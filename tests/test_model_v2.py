import copy
import json
import unittest
from pathlib import Path

from quality_queue.domain import load_snapshot
from quality_queue.model import ProposalError
from quality_queue.model_v2 import (
    admitted_input_v2, request_payload_v2, schema_v2, validate_v2_development,
)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = load_snapshot(ROOT / "data" / "packet-v1")
CUT = "2026-09-30T10:00:00+09:00"


def admitted():
    return admitted_input_v2(SNAPSHOT, "demo-investigator-a", CUT)


def valid_mock():
    q_current = "The confirmed record is four incorrectly labelled units among 50 inspected units."
    q_old = "Five incorrectly labelled units were recorded among 50 inspected units."
    unknown = "the total-lot defect count and cause remain unknown."
    return {
        "assertions": [
            {"field": "incorrect_units", "status": "current", "raw_value": "four",
             "source_id": "QDOC-002", "quote": q_current},
            {"field": "inspected_units", "status": "current", "raw_value": "50",
             "source_id": "QDOC-002", "quote": q_current},
            {"field": "incorrect_units", "status": "historical", "raw_value": "Five",
             "source_id": "QDOC-001", "quote": q_old},
            {"field": "inspected_units", "status": "historical", "raw_value": "50",
             "source_id": "QDOC-001", "quote": q_old},
            {"field": "current_cause", "status": "unknown", "raw_value": "unknown",
             "source_id": "QDOC-002", "quote": unknown},
        ],
        "evidence_request": {
            "question": "현재 원인을 확인할 원자료는 무엇입니까?",
            "source_id": "QDOC-002", "quote": unknown,
        },
    }


class ModelV2CPUContractTests(unittest.TestCase):
    def test_backend_admission_and_currentness_before_model(self):
        data = admitted()
        rows = {r["source_id"]: r for r in data["sources"]}
        self.assertEqual(rows["QDOC-001"]["source_state"], "historical")
        self.assertEqual(rows["QDOC-002"]["source_state"], "current")
        self.assertEqual(rows["QDOC-001"]["superseded_by_id"], "QDOC-002")
        self.assertEqual(rows["QDOC-002"]["supersedes_id"], "QDOC-001")
        self.assertNotIn("QDOC-010", rows)  # denied site
        self.assertNotIn("QDOC-011", rows)  # unavailable later record
        self.assertNotIn("typed", data)  # no answer packet or evaluator

    def test_early_cutoff_cannot_hint_future_correction(self):
        data = admitted_input_v2(SNAPSHOT, "demo-investigator-a",
                                 "2026-09-30T09:15:00+09:00")
        rows = {r["source_id"]: r for r in data["sources"]}
        self.assertEqual(rows["QDOC-001"]["source_state"], "current")
        self.assertIsNone(rows["QDOC-001"]["superseded_by_id"])
        self.assertNotIn("QDOC-002", json.dumps(data, ensure_ascii=False))

    def test_conflict_blocks_generation(self):
        with self.assertRaisesRegex(ProposalError, "current_source_conflict"):
            admitted_input_v2(SNAPSHOT, "demo-investigator-a", CUT, "QDOC-012")

    def test_schema_and_request_boundaries(self):
        schema = schema_v2()
        self.assertEqual(schema["properties"]["assertions"]["minItems"], 1)
        self.assertIn("historical", schema["properties"]["assertions"]["items"]["properties"]["status"]["enum"])
        request = request_payload_v2(admitted())
        self.assertFalse(request["think"])
        self.assertFalse(request["truncate"])
        self.assertFalse(request["shift"])
        self.assertEqual(request["options"]["num_ctx"], 4096)
        self.assertEqual(request["options"]["num_predict"], 512)
        self.assertNotIn("QDOC-010", request["messages"][1]["content"])

    def test_valid_mock_is_not_a_model_result(self):
        result = validate_v2_development(admitted(), json.dumps(valid_mock()))
        self.assertTrue(result["development_complete"])
        self.assertEqual(result["backend_only_rate_fraction"], "2/25")
        self.assertEqual(result["backend_only_rate_percent"], "8")
        self.assertTrue(result["question_semantic_review_needed"])

    def test_vacuous_and_incomplete_responses_fail(self):
        item = valid_mock()
        item["assertions"] = []
        with self.assertRaisesRegex(ProposalError, "assertion_count_invalid"):
            validate_v2_development(admitted(), json.dumps(item))
        item = valid_mock()
        item["assertions"] = item["assertions"][-1:]
        result = validate_v2_development(admitted(), json.dumps(item))
        self.assertFalse(result["development_complete"])
        self.assertEqual(len(result["missing_required_assertions"]), 4)

    def test_wrong_value_status_source_and_quote_fail(self):
        for key, value, error in (
            ("raw_value", "five", "quantity_not_supported_by_quote"),
            ("status", "historical", "source_status_mismatch"),
            ("source_id", "QDOC-001", "quote_missing_or_ambiguous"),
            ("quote", "No such source phrase", "quote_missing_or_ambiguous"),
        ):
            with self.subTest(key=key, value=value):
                item = valid_mock()
                item["assertions"][0][key] = value
                with self.assertRaisesRegex(ProposalError, error):
                    validate_v2_development(admitted(), json.dumps(item))

    def test_wrong_current_source_or_unsupported_extra_fails(self):
        item = valid_mock()
        item["assertions"][0]["source_id"] = "QDOC-004"
        with self.assertRaises(ProposalError):
            validate_v2_development(admitted(), json.dumps(item))
        item = valid_mock()
        item["assertions"].append({"field": "material_use", "status": "current",
                                   "raw_value": "yes", "source_id": "QDOC-002",
                                   "quote": item["assertions"][0]["quote"]})
        with self.assertRaisesRegex(ProposalError, "assertion_enum"):
            validate_v2_development(admitted(), json.dumps(item))

    def test_request_must_name_current_supported_unknown(self):
        item = valid_mock()
        item["evidence_request"]["source_id"] = "QDOC-001"
        with self.assertRaisesRegex(ProposalError, "request_source_not_current"):
            validate_v2_development(admitted(), json.dumps(item))
        item = valid_mock()
        item["evidence_request"]["question"] = "자료를 확인할까요?"
        self.assertFalse(validate_v2_development(admitted(), json.dumps(item))["development_complete"])

    def test_declared_schema_string_lengths_are_enforced_in_postvalidator(self):
        item = valid_mock()
        item["evidence_request"]["question"] = "원인" * 93 + "?"
        with self.assertRaisesRegex(ProposalError, "request_quote_or_text_invalid"):
            validate_v2_development(admitted(), json.dumps(item))
        item = valid_mock()
        item["assertions"][0]["raw_value"] = "four" * 26
        with self.assertRaisesRegex(ProposalError, "raw_value_invalid"):
            validate_v2_development(admitted(), json.dumps(item))
        item = valid_mock()
        item["assertions"][0]["quote"] = "x" * 301
        with self.assertRaisesRegex(ProposalError, "quote_invalid"):
            validate_v2_development(admitted(), json.dumps(item))


if __name__ == "__main__":
    unittest.main()
