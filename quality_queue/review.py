from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .baseline import build_packet
from .domain import Snapshot, SourceError, admit, canonical_hash, principal


class ReviewError(ValueError):
    pass


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    investigator: str
    reviewer: str
    cutoff: str
    capture_id: str | None
    packet_fingerprint: str
    decision: str
    reviewer_note: str
    at: str
    review_hash: str


class ReviewStore:
    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self._items: dict[str, Receipt] = {}
        self._dedupe: dict[tuple[str, str, str, str], str] = {}

    def replace_snapshot(self, snapshot: Snapshot) -> None:
        # The server can refresh immutable source bytes; old receipts remain for
        # stale comparison. This does not mutate any operational source.
        self.snapshot = snapshot

    def record(self, *, investigator: str, reviewer: str, cutoff: str,
               capture_id: str | None, packet_fingerprint: str,
               decision: str, reviewer_note: str = "") -> dict[str, Any]:
        if decision not in ("accepted_for_handoff", "returned"):
            raise ReviewError("review_decision_invalid")
        if not isinstance(reviewer_note, str) or len(reviewer_note) > 1000:
            raise ReviewError("review_note_invalid")
        actor = principal(reviewer)
        if actor.role != "reviewer":
            raise ReviewError("reviewer_role_required")
        packet = build_packet(self.snapshot, investigator, cutoff, capture_id)
        if packet["state"] == "scope_empty":
            raise ReviewError("scope_unavailable")
        if packet["packet_fingerprint"] != packet_fingerprint:
            raise ReviewError("packet_stale")
        visible = admit(self.snapshot, reviewer, cutoff, capture_id)
        allowed_ids = {source.id for source in visible.sources}
        investigator_visible = admit(self.snapshot, investigator, cutoff, capture_id)
        if not actor.allowed_sites or any(source.id not in allowed_ids
                                          for source in investigator_visible.sources):
            raise ReviewError("review_scope_denied")
        if decision == "accepted_for_handoff" and packet["state"] != "reviewer_ready_with_open_questions":
            raise ReviewError("handoff_blocked_by_source_conflict")
        key = (packet_fingerprint, reviewer, decision, reviewer_note)
        if key in self._dedupe:
            return self.status(self._dedupe[key], investigator, reviewer)
        now = datetime.now(timezone.utc).isoformat()
        receipt_id = uuid.uuid4().hex
        signature = canonical_hash({"receipt_id": receipt_id, "fingerprint": packet_fingerprint,
                                    "investigator": investigator, "reviewer": reviewer,
                                    "cutoff": cutoff, "capture_id": capture_id,
                                    "decision": decision, "note": reviewer_note, "at": now})
        receipt = Receipt(receipt_id, investigator, reviewer, cutoff, capture_id,
                          packet_fingerprint, decision, reviewer_note, now, signature)
        self._items[receipt_id] = receipt
        self._dedupe[key] = receipt_id
        return self.status(receipt_id, investigator, reviewer)

    def status(self, receipt_id: str, investigator: str, reviewer: str) -> dict[str, Any]:
        receipt = self._items.get(receipt_id)
        if receipt is None or receipt.investigator != investigator or receipt.reviewer != reviewer:
            raise ReviewError("receipt_unavailable")
        actor = principal(reviewer)
        if actor.role != "reviewer" or not actor.allowed_sites:
            raise ReviewError("review_scope_denied")
        packet = build_packet(self.snapshot, investigator, receipt.cutoff, receipt.capture_id)
        visible = admit(self.snapshot, reviewer, receipt.cutoff, receipt.capture_id)
        allowed_ids = {source.id for source in visible.sources}
        investigator_visible = admit(self.snapshot, investigator, receipt.cutoff, receipt.capture_id)
        authorized = all(source.id in allowed_ids for source in investigator_visible.sources)
        if not authorized or packet["state"] == "scope_empty":
            raise ReviewError("review_scope_denied")
        fresh = packet["packet_fingerprint"] == receipt.packet_fingerprint
        return {"receipt_id": receipt.receipt_id,
                "decision": receipt.decision if fresh else "stale",
                "original_decision": receipt.decision,
                "fresh": fresh, "at": receipt.at,
                "cutoff": receipt.cutoff, "capture_id": receipt.capture_id,
                "packet_fingerprint": receipt.packet_fingerprint,
                "reviewer_note": receipt.reviewer_note,
                "review_hash": receipt.review_hash,
                "handoff_only": True, "operational_source_state_unchanged": True}

    def export(self, receipt_id: str, investigator: str, reviewer: str,
               cutoff: str, capture_id: str | None = None) -> dict[str, Any]:
        receipt = self._items.get(receipt_id)
        if receipt is None or receipt.investigator != investigator or receipt.reviewer != reviewer:
            raise ReviewError("receipt_unavailable")
        if receipt.cutoff != cutoff or receipt.capture_id != capture_id:
            raise ReviewError("receipt_not_admitted_at_cutoff")
        current = build_packet(self.snapshot, investigator, cutoff, capture_id)
        if current["state"] == "scope_empty":
            raise ReviewError("review_scope_denied")
        status = self.status(receipt_id, investigator, reviewer)
        if not status["fresh"] or status["decision"] != "accepted_for_handoff" or \
                status["packet_fingerprint"] != current["packet_fingerprint"]:
            raise ReviewError("reviewed_handoff_unavailable")
        # Free-form notes remain in the server receipt. They are not an admitted
        # source projection and must not cross a cutoff through a read API.
        public_status = {key: value for key, value in status.items() if key != "reviewer_note"}
        return {"receipt": public_status, "packet": current,
                "statement": "검토용 인계 기록입니다. 미해결 근거 요청이 남아 있으며 운영 원본, 로트 처분, CAPA 상태는 변경되지 않았습니다."}

    def list_for(self, investigator: str, reviewer: str, cutoff: str,
                 capture_id: str | None = None) -> list[dict[str, Any]]:
        current = build_packet(self.snapshot, investigator, cutoff, capture_id)
        if current["state"] == "scope_empty":
            return []
        projected = []
        for item in self._items.values():
            if item.investigator != investigator or item.reviewer != reviewer or \
                    item.cutoff != cutoff or item.capture_id != capture_id:
                continue
            status = self.status(item.receipt_id, investigator, reviewer)
            # Keep full receipt and note privately; only current-admitted,
            # source-free metadata is returned to history views.
            projected.append({key: value for key, value in status.items()
                              if key != "reviewer_note"})
        return projected
