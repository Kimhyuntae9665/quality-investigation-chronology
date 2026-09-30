from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from .domain import (
    Admitted, Replay, Snapshot, Source, SourceError, admit, canonical_hash,
    exact_span, packet_fingerprint, replay,
)

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10}
INSPECTION = re.compile(
    r"\b(?P<wrong>\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r" incorrectly labelled units\b"
    r"(?P<middle>[^.]{0,120}?)"
    r"\b(?:among|of)\s+(?P<checked>\d+)\s+inspected units\b",
    re.IGNORECASE,
)
WRONG_ONLY = re.compile(
    r"\b(?P<wrong>\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r" incorrectly labelled units\b", re.IGNORECASE,
)
LOT_TOTAL = re.compile(r"\bTotal lot quantity(?::| remains)?\s*(\d+)\s+units\b",
                       re.IGNORECASE)
PRODUCT = re.compile(r"\bP-\d+\b")
LINE = re.compile(r"\bPKG-\d+\b")


def _number(value: str) -> int:
    return int(value) if value.isdecimal() else WORDS[value.casefold()]


def ref(row: Source, quote: str) -> dict[str, Any]:
    start, end = exact_span(row, quote)
    return {"source_id": row.id, "source_system": row.source_system,
            "logical_id": row.logical_id, "revision": row.revision,
            "site": row.site, "case_id": row.case_id,
            "source_text_sha256": row.content_sha256,
            "source_envelope_sha256": row.envelope_sha256,
            "span_start_codepoint": start, "span_end_codepoint_exclusive": end,
            "quote": quote}


def _find(rows: tuple[Source, ...], kind: str) -> Source | None:
    found = [row for row in rows if row.record_type == kind]
    return found[0] if len(found) == 1 else None


def _request(code: str, question: str, row: Source, quote: str) -> dict[str, Any]:
    return {"request_id": code, "state": "open_question", "question": question,
            "source": ref(row, quote), "sent_externally": False}


def _measurement(row: Source | None, conflict: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sample = {"incorrect_units": None, "inspected_units": None, "rate_fraction": None,
              "rate_percent": None, "quantity_grain": "inspected_sample",
              "lot_total_units": None, "lot_defect_units": None,
              "state": "unknown_due_to_conflict" if conflict else "not_evidenced",
              "source": None}
    requests = []
    if row is None:
        return sample, requests
    full = INSPECTION.search(row.text)
    short = WRONG_ONLY.search(row.text)
    if full:
        wrong, checked = _number(full.group("wrong")), int(full.group("checked"))
        if checked > 0 and wrong <= checked:
            ratio = Fraction(wrong, checked)
            percentage = ratio * 100
            sample.update({"incorrect_units": wrong, "inspected_units": checked,
                           "rate_fraction": f"{ratio.numerator}/{ratio.denominator}",
                           "rate_percent": percentage.numerator if percentage.denominator == 1 else None,
                           "state": "supported_sample",
                           "source": ref(row, full.group(0))})
        else:
            sample["state"] = "invalid_inspection_values"
            requests.append(_request("REQ-SAMPLE-VERIFY", "검사 수량과 오류 수량을 확인해 주세요.",
                                     row, full.group(0)))
    elif short:
        sample.update({"incorrect_units": _number(short.group("wrong")),
                       "state": "inspected_denominator_missing",
                       "source": ref(row, short.group(0))})
        requests.append(_request("REQ-SAMPLE-DENOMINATOR",
                                 "검사한 표본 수량의 근거를 요청합니다. 로트 총수량으로 대체하지 않습니다.",
                                 row, short.group(0)))
    else:
        sample["state"] = "inspection_wording_unparsed"
        requests.append(_request("REQ-SAMPLE-WORDING",
                                 "검사 표본의 분자·분모를 원문에서 다시 확인해 주세요.",
                                 row, row.text))
    lot = LOT_TOTAL.search(row.text)
    if lot:
        sample["lot_total_units"] = int(lot.group(1))
    return sample, requests


def _extract(current: tuple[Source, ...], replayed: Replay,
             admitted: Admitted, current_case_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    current_rows = tuple(r for r in current if r.case_id == current_case_id)
    observation_conflict = any(family[2] == current_case_id and family[3] == "OBS-040"
                               for family in replayed.conflicted_families)
    inspection = _find(current_rows, "inspection_record") or _find(current_rows, "inspection_correction")
    sample, requests = _measurement(inspection, observation_conflict)
    if observation_conflict:
        related = [r for r in replayed.conflicted if r.case_id == current_case_id and r.logical_id == "OBS-040"]
        sample["state"] = "unknown_due_to_conflict"
        sample["source"] = None
        if related:
            requests.append(_request("REQ-OBS-CONFLICT",
                                     "동일 revision의 상충하는 검사 기록을 원천 시스템에서 조정해 주세요.",
                                     related[0], related[0].text))
    conclusion = _find(current_rows, "investigation_conclusion")
    if conclusion:
        cause = {"status": "reported_conclusion_available",
                 "description": "원문에 현재 사건의 결론 보고가 기록됨",
                 "independently_verified_by_app": False,
                 "source": ref(conclusion, conclusion.text)}
        requests.append(_request("REQ-CAUSE-RAW",
                                 "보고된 결론의 기초 원시 조사기록을 요청합니다.",
                                 conclusion, "The underlying raw investigation records are not part of this export."))
    else:
        cause = {"status": "not_established_at_cutoff", "description": None,
                 "independently_verified_by_app": False, "source": None}
        if inspection:
            phrase = "cause remain unknown" if "cause remain unknown" in inspection.text else "Cause has not been established"
            if phrase in inspection.text:
                requests.append(_request("REQ-CAUSE-EVIDENCE",
                                         "현재 사건 원인 판단에 필요한 원시 조사 근거를 요청합니다.",
                                         inspection, phrase))
    containment_row = _find(current_rows, "containment_record")
    containment = {"recorded_status": None, "physical_coverage": "unknown", "source": None}
    if containment_row and "HOLD" in containment_row.text:
        containment.update({"recorded_status": "HOLD",
                            "source": ref(containment_row, "status was recorded as HOLD")})
        requests.append(_request("REQ-HOLD-COVERAGE",
                                 "실물 수량의 위치와 격리 범위를 확인할 근거를 요청합니다.",
                                 containment_row,
                                 "This record does not confirm that every physical unit has been located or segregated."))
    material_row = _find(current_rows, "material_issue_record")
    material = {"issued_id": None, "installation_or_use": "unknown", "source": None}
    if material_row:
        match = re.search(r"\bLabel roll (R-\d+) was issued\b", material_row.text)
        if match:
            material.update({"issued_id": match.group(1),
                             "source": ref(material_row, match.group(0))})
        requests.append(_request("REQ-ROLL-INSTALL",
                                 "발행된 라벨 롤의 실제 장착·사용 시각 근거를 요청합니다.",
                                 material_row,
                                 "No installation time, removal time or proof of use during the 09:00 inspection is available in this exported record."))
    action_row = _find(current_rows, "action_tracker")
    action = {"implementation": "not_evidenced", "effectiveness": "not_evidenced", "source": None}
    if action_row:
        if "was implemented" in action_row.text:
            action["implementation"] = "recorded"
        if "Effectiveness review is scheduled" in action_row.text and "No completed effectiveness result" in action_row.text:
            action["effectiveness"] = "scheduled_no_result"
        action["source"] = ref(action_row, action_row.text)
        requests.append(_request("REQ-ACTION-EFFECTIVENESS",
                                 "완료된 효과성 평가 기록을 요청합니다. 실행 기록만으로 효과를 확정하지 않습니다.",
                                 action_row, "No completed effectiveness result is available."))
    briefing_row = _find(current_rows, "briefing_record")
    briefing = {"occurrence": "not_evidenced", "attendance_attachment": "unknown",
                "individual_attendance": "not_established", "source": None}
    if briefing_row:
        briefing["occurrence"] = "recorded"
        briefing["source"] = ref(briefing_row, "a briefing occurred at 09:45")
        absence = any(not x["present_in_export"] and x["referenced_by"] == briefing_row.id
                      for x in admitted.attachments)
        if absence:
            briefing["attendance_attachment"] = "absent_from_export"
            requests.append(_request("REQ-ATTENDANCE-ATTACHMENT",
                                     "브리핑 참석 첨부자료를 요청합니다. 미첨부가 불참을 뜻하지 않습니다.",
                                     briefing_row, "That attachment is not present in this export."))
    typed = {"sample": sample, "current_cause": cause, "containment": containment,
             "material": material, "action": action, "briefing": briefing}
    return typed, requests


def _comparisons(snapshot: Snapshot, current: tuple[Source, ...]) -> list[dict[str, Any]]:
    current_case_rows = [row for row in current if row.case_id == snapshot.current_case_id]
    if not current_case_rows:
        return []
    current_text = " ".join(row.text for row in current_case_rows)
    current_products = set(PRODUCT.findall(current_text))
    current_lines = set(LINE.findall(current_text))
    cases = sorted({row.case_id for row in current if row.case_id != snapshot.current_case_id})
    output = []
    for case_id in cases:
        rows = [row for row in current if row.case_id == case_id]
        text = " ".join(row.text for row in rows)
        products = set(PRODUCT.findall(text))
        lines = set(LINE.findall(text))
        output.append({
            "case_id": case_id, "precedent_only": True,
            "same_products": sorted(current_products & products),
            "same_lines": sorted(current_lines & lines),
            "different_products": sorted(products - current_products),
            "different_lines": sorted(lines - current_lines),
            "historical_sources": [ref(row, row.text) for row in rows],
            "current_cause_inferred": False,
        })
    output.sort(key=lambda x: (-len(x["same_products"])-len(x["same_lines"]), x["case_id"]))
    return output


def build_packet(snapshot: Snapshot, principal_id: str, cutoff: str,
                 capture_id: str | None = None) -> dict[str, Any]:
    scope = admit(snapshot, principal_id, cutoff, capture_id)
    replayed = replay(scope.sources)
    current = replayed.current
    has_current = any(row.case_id == snapshot.current_case_id for row in scope.sources)
    if not has_current:
        return {"state": "scope_empty", "scope": {"principal_id": principal_id,
                "role": scope.principal.role, "allowed_sites": list(scope.principal.allowed_sites),
                "cutoff": cutoff}, "timeline": [], "corrections": [],
                "comparisons": [], "requests": [], "typed": None,
                "packet_fingerprint": None}
    typed, requests = _extract(current, replayed, scope, snapshot.current_case_id)
    comparisons = _comparisons(snapshot, current)
    timeline = [
        {"source_id": row.id, "case_id": row.case_id, "record_type": row.record_type,
         "event_at": row.event_at, "recorded_at": row.recorded_at,
         "revision": row.revision, "content_sha256": row.content_sha256,
         "envelope_sha256": row.envelope_sha256,
         "timeline_state": "current_source", "text": row.text}
        for row in current if row.case_id == snapshot.current_case_id
    ]
    correction_ids = {row.id for row in replayed.superseded}
    corrections = [
        {"source_id": row.id, "case_id": row.case_id, "revision": row.revision,
         "superseded": row.id in correction_ids,
         "recorded_at": row.recorded_at, "event_at": row.event_at,
         "content_sha256": row.content_sha256,
         "envelope_sha256": row.envelope_sha256, "text": row.text}
        for row in replayed.superseded
        if row.case_id == snapshot.current_case_id
    ]
    conflicted = [row.id for row in replayed.conflicted if row.case_id == snapshot.current_case_id]
    state = "blocked_source_conflict" if conflicted else "reviewer_ready_with_open_questions"
    proposal_hash = canonical_hash({"typed": typed, "comparisons": comparisons,
                                    "timeline": timeline, "corrections": corrections})
    question_hash = canonical_hash(requests)
    fingerprint = packet_fingerprint(snapshot, scope, scope.sources, proposal_hash, question_hash)
    return {
        "state": state,
        "scope": {"principal_id": principal_id, "role": scope.principal.role,
                  "allowed_sites": list(scope.principal.allowed_sites),
                  "cutoff": cutoff, "capture_id": capture_id,
                  "fixture_id": snapshot.fixture_id, "rule_version": "p10_cpu_baseline_v1"},
        "current_case_id": snapshot.current_case_id,
        "timeline": timeline, "corrections": corrections,
        "conflicted_source_ids": conflicted, "comparisons": comparisons,
        "typed": typed, "requests": requests,
        "packet_fingerprint": fingerprint,
        "handoff_only": True, "operational_source_state_unchanged": True,
    }
