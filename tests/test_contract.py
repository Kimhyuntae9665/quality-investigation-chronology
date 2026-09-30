import json
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from quality_queue.baseline import build_packet
from quality_queue.domain import SourceError, admit, exact_span, load_snapshot, replay
from quality_queue.review import ReviewError, ReviewStore
from quality_queue.server import App

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = load_snapshot(ROOT / "data" / "packet-v1")
A = "demo-investigator-a"
REVIEWER = "demo-reviewer-a"
CUT_EARLY = "2026-09-30T09:15:00+09:00"
CUT_CORRECTION = "2026-09-30T09:20:00+09:00"
CUT_DEFAULT = "2026-09-30T10:00:00+09:00"
CUT_LATER = "2026-09-30T10:30:00+09:00"


def packet(cutoff=CUT_DEFAULT, capture=None, actor=A):
    return build_packet(SNAPSHOT, actor, cutoff, capture)


class ChronologyContractTests(unittest.TestCase):
    def test_pre_correction_only_original_at_same_event_time(self):
        view = packet(CUT_EARLY)
        sample = view["typed"]["sample"]
        self.assertEqual((sample["incorrect_units"], sample["inspected_units"], sample["rate_percent"]), (5, 50, 10))
        self.assertEqual(sample["lot_total_units"], 500)
        self.assertEqual(sample["lot_defect_units"], None)
        self.assertIn("QDOC-001", [x["source_id"] for x in view["timeline"]])
        self.assertNotIn("QDOC-002", json.dumps(view, ensure_ascii=False))
        self.assertNotIn("QDOC-012", json.dumps(view, ensure_ascii=False))
        self.assertEqual(view["corrections"], [])

    def test_inclusive_correction_and_old_record_history_only(self):
        view = packet(CUT_CORRECTION)
        sample = view["typed"]["sample"]
        self.assertEqual((sample["incorrect_units"], sample["inspected_units"], sample["rate_percent"]), (4, 50, 8))
        self.assertIn("QDOC-002", [x["source_id"] for x in view["timeline"]])
        self.assertNotIn("QDOC-001", [x["source_id"] for x in view["timeline"]])
        self.assertIn("QDOC-001", [x["source_id"] for x in view["corrections"]])
        old = next(x for x in view["corrections"] if x["source_id"] == "QDOC-001")
        self.assertEqual(old["event_at"], "2026-09-30T09:00:00+09:00")
        self.assertTrue(old["superseded"])

    def test_default_open_questions_are_compatible_with_handoff(self):
        view = packet()
        self.assertEqual(view["state"], "reviewer_ready_with_open_questions")
        self.assertEqual(view["typed"]["sample"]["rate_fraction"], "2/25")
        self.assertEqual(len(view["requests"]), 5)
        self.assertFalse(view["typed"]["current_cause"]["independently_verified_by_app"])
        self.assertEqual(view["typed"]["material"]["installation_or_use"], "unknown")
        self.assertEqual(view["typed"]["containment"]["physical_coverage"], "unknown")
        self.assertEqual(view["typed"]["action"]["effectiveness"], "scheduled_no_result")
        self.assertEqual(view["typed"]["briefing"]["individual_attendance"], "not_established")

    def test_historical_cause_not_current_cause(self):
        view = packet()
        self.assertEqual(len(view["comparisons"]), 2)
        self.assertTrue(all(c["precedent_only"] and not c["current_cause_inferred"]
                            for c in view["comparisons"]))
        self.assertEqual(view["typed"]["current_cause"]["status"], "not_established_at_cutoff")

    def test_post_cutoff_conclusion_not_visible_early(self):
        early = packet()
        later = packet("2026-09-30T11:05:00+09:00")
        self.assertNotIn("QDOC-011", json.dumps(early, ensure_ascii=False))
        self.assertEqual(later["typed"]["current_cause"]["status"], "reported_conclusion_available")
        self.assertFalse(later["typed"]["current_cause"]["independently_verified_by_app"])
        self.assertIn("REQ-CAUSE-RAW", [r["request_id"] for r in later["requests"]])

    def test_unavailable_later_capture_does_not_erase_last_admitted_source(self):
        with self.assertRaisesRegex(SourceError, "capture_unavailable"):
            packet(CUT_DEFAULT, "QDOC-013")
        view = packet(CUT_DEFAULT)
        self.assertEqual(view["typed"]["sample"]["incorrect_units"], 4)

    def test_conflicting_same_revision_blocks_family_and_handoff(self):
        view = packet(CUT_DEFAULT, "QDOC-012")
        self.assertEqual(view["state"], "blocked_source_conflict")
        self.assertEqual(view["typed"]["sample"]["state"], "unknown_due_to_conflict")
        self.assertIsNone(view["typed"]["sample"]["rate_percent"])
        self.assertEqual(view["typed"]["sample"]["lot_defect_units"], None)
        self.assertEqual(set(view["conflicted_source_ids"]), {"QDOC-001", "QDOC-002", "QDOC-012"})
        self.assertNotIn("QDOC-001", [x["source_id"] for x in view["timeline"]])

    def test_conflict_context_unknown_is_not_a_proven_product_difference(self):
        view = packet(CUT_DEFAULT, "QDOC-012")
        precedent = next(item for item in view["comparisons"] if item["case_id"] == "D-020")
        self.assertNotIn("P-100", precedent["different_products"])
        self.assertIn("P-100", precedent["unknown_products"])
        self.assertEqual({row["source_id"] for row in view["conflicted_sources"]},
                         {"QDOC-001", "QDOC-002", "QDOC-012"})
        self.assertTrue(all(row["source_state"] == "conflicted"
                            for row in view["conflicted_sources"]))
        self.assertNotIn("QDOC-010", json.dumps(view))

    def test_later_mutually_exclusive_correction(self):
        view = packet(CUT_LATER, "QDOC-013")
        self.assertEqual(view["typed"]["sample"]["rate_percent"], 6)
        self.assertIn("QDOC-013", [x["source_id"] for x in view["timeline"]])
        self.assertEqual({x["source_id"] for x in view["corrections"]}, {"QDOC-001", "QDOC-002"})

    def test_missing_sample_denominator_does_not_use_lot_total(self):
        view = packet(CUT_LATER, "QDOC-014")
        sample = view["typed"]["sample"]
        self.assertEqual(sample["state"], "inspected_denominator_missing")
        self.assertEqual(sample["incorrect_units"], 4)
        self.assertIsNone(sample["inspected_units"])
        self.assertIsNone(sample["rate_percent"])
        self.assertIn("REQ-SAMPLE-DENOMINATOR", [r["request_id"] for r in view["requests"]])

    def test_site_admission_precedes_replay_and_comparison(self):
        view = packet()
        all_text = json.dumps(view, ensure_ascii=False)
        self.assertNotIn("QDOC-010", all_text)
        self.assertNotIn("D-030", all_text)
        empty = packet(actor="demo-no-sites")
        self.assertEqual(empty["state"], "scope_empty")
        self.assertEqual(empty["timeline"], [])
        self.assertEqual(empty["comparisons"], [])

    def test_exact_quote_span_and_ambiguous_quote(self):
        row = next(x for x in SNAPSHOT.base if x.id == "QDOC-002")
        quote = "four incorrectly labelled units"
        start, end = exact_span(row, quote)
        self.assertEqual(row.text[start:end], quote)
        with self.assertRaisesRegex(SourceError, "quote_not_in_source"):
            exact_span(row, "40 incorrectly labelled units")
        with self.assertRaisesRegex(SourceError, "quote_ambiguous"):
            exact_span(row, "e")

    def test_packet_fingerprint_tracks_cutoff_and_capture(self):
        base = packet()
        self.assertNotEqual(base["packet_fingerprint"], packet(CUT_EARLY)["packet_fingerprint"])
        self.assertNotEqual(base["packet_fingerprint"], packet(CUT_DEFAULT, "QDOC-012")["packet_fingerprint"])


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.store = ReviewStore(SNAPSHOT)

    def accept(self, cutoff=CUT_DEFAULT):
        view = packet(cutoff)
        return self.store.record(investigator=A, reviewer=REVIEWER, cutoff=cutoff,
                                 capture_id=None, packet_fingerprint=view["packet_fingerprint"],
                                 decision="accepted_for_handoff", reviewer_note="fictional review")

    def test_accept_open_questions_and_export_without_closure(self):
        receipt = self.accept()
        self.assertEqual(receipt["decision"], "accepted_for_handoff")
        exported = self.store.export(receipt["receipt_id"], A, REVIEWER)
        self.assertEqual(len(exported["packet"]["requests"]), 5)
        self.assertIn("CAPA", exported["statement"])
        self.assertTrue(exported["packet"]["operational_source_state_unchanged"])

    def test_duplicate_acceptance_idempotent(self):
        self.assertEqual(self.accept()["receipt_id"], self.accept()["receipt_id"])

    def test_changed_review_note_is_new_receipt_and_exact_repeat_is_idempotent(self):
        first = self.accept()
        view = packet(CUT_DEFAULT)
        second = self.store.record(investigator=A, reviewer=REVIEWER,
                                   cutoff=CUT_DEFAULT, capture_id=None,
                                   packet_fingerprint=view["packet_fingerprint"],
                                   decision="accepted_for_handoff",
                                   reviewer_note="revised fictional review")
        self.assertNotEqual(first["receipt_id"], second["receipt_id"])
        self.assertEqual(second["reviewer_note"], "revised fictional review")
        self.assertEqual(len(self.store.list_for(A, REVIEWER)), 2)
        repeat = self.store.record(investigator=A, reviewer=REVIEWER,
                                   cutoff=CUT_DEFAULT, capture_id=None,
                                   packet_fingerprint=view["packet_fingerprint"],
                                   decision="accepted_for_handoff",
                                   reviewer_note="revised fictional review")
        self.assertEqual(repeat["receipt_id"], second["receipt_id"])

    def test_source_conflict_blocks_acceptance(self):
        view = packet(CUT_DEFAULT, "QDOC-012")
        with self.assertRaisesRegex(ReviewError, "handoff_blocked_by_source_conflict"):
            self.store.record(investigator=A, reviewer=REVIEWER, cutoff=CUT_DEFAULT,
                              capture_id="QDOC-012", packet_fingerprint=view["packet_fingerprint"],
                              decision="accepted_for_handoff")

    def test_stale_packet_rejected_before_recording(self):
        with self.assertRaisesRegex(ReviewError, "packet_stale"):
            self.store.record(investigator=A, reviewer=REVIEWER, cutoff=CUT_DEFAULT,
                              capture_id=None, packet_fingerprint=packet(CUT_EARLY)["packet_fingerprint"],
                              decision="accepted_for_handoff")

    def test_source_change_invalidates_export(self):
        receipt = self.accept()
        changed = replace(SNAPSHOT, source_file_hashes={**SNAPSHOT.source_file_hashes,
                           "source-corpus.json": "0" * 64})
        self.store.replace_snapshot(changed)
        status = self.store.status(receipt["receipt_id"], A, REVIEWER)
        self.assertFalse(status["fresh"])
        self.assertEqual(status["decision"], "stale")
        with self.assertRaisesRegex(ReviewError, "reviewed_handoff_unavailable"):
            self.store.export(receipt["receipt_id"], A, REVIEWER)

    def test_wrong_reviewer_or_role_rejected(self):
        view = packet()
        with self.assertRaisesRegex(ReviewError, "reviewer_role_required"):
            self.store.record(investigator=A, reviewer=A, cutoff=CUT_DEFAULT,
                              capture_id=None, packet_fingerprint=view["packet_fingerprint"],
                              decision="accepted_for_handoff")
        receipt = self.accept()
        with self.assertRaisesRegex(ReviewError, "receipt_unavailable"):
            self.store.status(receipt["receipt_id"], A, "demo-investigator-b")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = App(0)
        cls.thread = threading.Thread(target=cls.app.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.app.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown()
        cls.app.server_close()
        cls.thread.join(timeout=5)

    def get(self, path, query=None):
        url = self.base + path + ("?" + urlencode(query) if query else "")
        try:
            with urlopen(url, timeout=4) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_health_explicitly_cpu_fictional(self):
        code, body = self.get("/api/health")
        self.assertEqual(code, 200)
        self.assertEqual((body["fictional"], body["model_enabled"], body["qms_writes"]), (True, False, False))

    def test_pre_cutoff_api_view_and_source_cannot_hint_future(self):
        query = {"investigator": A, "cutoff": CUT_EARLY}
        code, body = self.get("/api/view", query)
        self.assertEqual(code, 200)
        self.assertEqual(body["typed"]["sample"]["rate_percent"], 10)
        self.assertNotIn("QDOC-002", json.dumps(body))
        code, body = self.get("/api/source/QDOC-002", query)
        self.assertEqual((code, body["error"]), (404, "source_unavailable"))

    def test_unavailable_capture_has_uniform_error_and_no_selection(self):
        code, body = self.get("/api/scenarios", {"investigator": A, "cutoff": CUT_DEFAULT})
        self.assertEqual(code, 200)
        self.assertEqual([row["capture_id"] for row in body["captures"]], ["QDOC-012"])
        code, body = self.get("/api/view", {"investigator": A, "cutoff": CUT_DEFAULT,
                                             "capture_id": "QDOC-013"})
        self.assertEqual((code, body["error"]), (404, "capture_unavailable"))

    def test_denied_site_source_returns_same_unavailable_response(self):
        code, body = self.get("/api/source/QDOC-010", {"investigator": A, "cutoff": CUT_DEFAULT})
        self.assertEqual((code, body["error"]), (404, "source_unavailable"))
        code, body = self.get("/api/source/absent", {"investigator": A, "cutoff": CUT_DEFAULT})
        self.assertEqual((code, body["error"]), (404, "source_unavailable"))

    def test_source_span_roundtrip(self):
        row = next(r for r in SNAPSHOT.base if r.id == "QDOC-002")
        quote = "four incorrectly labelled units"
        code, body = self.get("/api/source/QDOC-002", {"investigator": A, "cutoff": CUT_DEFAULT, "quote": quote})
        self.assertEqual(code, 200)
        start, end = body["quote_span"]
        self.assertEqual(body["text"][start:end], quote)
        self.assertEqual(body["content_sha256"], row.content_sha256)

    def test_reject_cross_origin(self):
        request = Request(self.base + "/api/view", headers={"Origin": "https://example.org"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=4)
        self.assertEqual(caught.exception.code, 403)

    def test_malformed_review_types_return_json_400(self):
        for bad in ({"reviewer": []}, {"capture_id": []}, {"investigator": []}):
            body = json.dumps(bad).encode("utf-8")
            request = Request(self.base + "/api/review", data=body, method="POST",
                              headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=4)
            self.assertEqual(caught.exception.code, 400)
            self.assertEqual(json.load(caught.exception)["error"], "review_payload_invalid")




class ModelPreflightCpuTests(unittest.TestCase):
    def model_input(self, cutoff=CUT_DEFAULT):
        from quality_queue.model import admitted_input
        return admitted_input(SNAPSHOT, A, cutoff)

    def valid(self):
        return {
            "response_state": "proposed",
            "observations": [
                {"field": "sample_wrong", "value": "4", "source_id": "QDOC-002",
                 "quote": "four incorrectly labelled units among 50 inspected units"},
                {"field": "sample_inspected", "value": "50", "source_id": "QDOC-002",
                 "quote": "four incorrectly labelled units among 50 inspected units"},
            ],
            "questions": [
                {"question": "현재 원인의 원시 근거는 어디에 있나요?",
                 "source_id": "QDOC-002", "quote": "cause remain unknown"},
            ],
            "abstain_reason": "",
        }

    def test_only_admitted_current_case_sources_enter_model_input(self):
        payload = self.model_input()
        ids = {x["source_id"] for x in payload["sources"]}
        self.assertIn("QDOC-002", ids)
        self.assertNotIn("QDOC-001", ids)
        self.assertNotIn("QDOC-010", ids)
        self.assertNotIn("QDOC-011", ids)
        self.assertNotIn("QDOC-007", ids)
        self.assertNotIn("QDOC-008", ids)
        self.assertNotIn("QDOC-009", ids)
        early = self.model_input(CUT_EARLY)
        early_ids = {x["source_id"] for x in early["sources"]}
        self.assertIn("QDOC-001", early_ids)
        self.assertNotIn("QDOC-002", early_ids)

    def test_conflict_prevents_model_input(self):
        from quality_queue.model import ProposalError, admitted_input
        with self.assertRaisesRegex(ProposalError, "current_source_conflict"):
            admitted_input(SNAPSHOT, A, CUT_DEFAULT, "QDOC-012")

    def test_model_request_is_bounded_and_does_not_contain_baseline_answer(self):
        from quality_queue.model import request_payload
        payload = request_payload(self.model_input())
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertFalse(payload["truncate"])
        self.assertFalse(payload["shift"])
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertEqual(payload["options"]["num_predict"], 320)
        self.assertNotIn("typed", payload["messages"][1]["content"])
        self.assertNotIn("evaluation", payload["messages"][1]["content"])

    def test_exact_quoted_development_proposal(self):
        from quality_queue.model import validate_proposal
        result = validate_proposal(self.model_input(), json.dumps(self.valid()))
        self.assertTrue(result["complete_for_development_case"])
        self.assertEqual(result["observed_values"], {"sample_wrong": "4", "sample_inspected": "50"})
        self.assertEqual(result["question_count"], 1)

    def test_empty_json_is_failure_even_if_schema_fields_exist(self):
        from quality_queue.model import validate_proposal
        empty = {"response_state": "proposed", "observations": [], "questions": [], "abstain_reason": ""}
        result = validate_proposal(self.model_input(), json.dumps(empty))
        self.assertFalse(result["complete_for_development_case"])
        self.assertEqual(result["failure"], "incomplete_or_abstained")

    def test_wrong_value_with_real_quote_is_rejected(self):
        from quality_queue.model import ProposalError, validate_proposal
        bad = self.valid()
        bad["observations"][0]["value"] = "40"
        with self.assertRaisesRegex(ProposalError, "value_not_supported_by_quote"):
            validate_proposal(self.model_input(), json.dumps(bad))

    def test_denied_or_old_source_cannot_support_proposal(self):
        from quality_queue.model import ProposalError, validate_proposal
        for sid in ("QDOC-001", "QDOC-010"):
            bad = self.valid()
            bad["observations"][0]["source_id"] = sid
            with self.assertRaisesRegex(ProposalError, "source_not_admitted"):
                validate_proposal(self.model_input(), json.dumps(bad))

    def test_quote_must_be_exact_and_nonambiguous(self):
        from quality_queue.model import ProposalError, validate_proposal
        bad = self.valid()
        bad["observations"][0]["quote"] = "4 incorrectly labelled units among 50 inspected units"
        with self.assertRaisesRegex(ProposalError, "quote_missing_or_ambiguous"):
            validate_proposal(self.model_input(), json.dumps(bad))



class TamperAndRevocationTests(unittest.TestCase):
    def test_changed_public_source_bytes_fail_manifest_check(self):
        import shutil
        import tempfile
        from quality_queue.domain import load_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in ("source-manifest.json", "source-corpus.json",
                         "additional-source-captures.json"):
                shutil.copy(ROOT / "data" / "packet-v1" / name, folder / name)
            target = folder / "source-corpus.json"
            target.write_bytes(target.read_bytes() + b" ")
            with self.assertRaisesRegex(SourceError, "source_file_hash_mismatch"):
                load_snapshot(folder)

    def test_revoked_reviewer_scope_blocks_old_receipt_export(self):
        from unittest.mock import patch
        from quality_queue.domain import PRINCIPALS
        store = ReviewStore(SNAPSHOT)
        view = packet()
        receipt = store.record(investigator=A, reviewer=REVIEWER, cutoff=CUT_DEFAULT,
                               capture_id=None, packet_fingerprint=view["packet_fingerprint"],
                               decision="accepted_for_handoff")
        with patch.dict(PRINCIPALS, {REVIEWER: ("reviewer", ())}):
            with self.assertRaisesRegex(ReviewError, "review_scope_denied"):
                store.export(receipt["receipt_id"], A, REVIEWER)

if __name__ == "__main__":
    unittest.main()
