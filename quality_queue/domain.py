from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RULE_VERSION = "p10_cpu_admission_replay_v1"
PRINCIPALS = {
    "demo-investigator-a": ("investigator", ("PLANT-A",)),
    "demo-reviewer-a": ("reviewer", ("PLANT-A",)),
    "demo-investigator-b": ("investigator", ("PLANT-B",)),
    "demo-no-sites": ("investigator", ()),
}


class SourceError(ValueError):
    pass


def parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise SourceError(label + "_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SourceError(label + "_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceError(label + "_timezone_required")
    return parsed.astimezone(timezone.utc)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_hash(obj: Any) -> str:
    return digest(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8"))


def source_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not 2 <= len(value) <= 100 or value.strip() != value:
        raise SourceError(label + "_invalid")
    if any(ord(ch) < 33 for ch in value) or "/" in value or "\\" in value:
        raise SourceError(label + "_invalid")
    return value


@dataclass(frozen=True)
class Principal:
    principal_id: str
    role: str
    allowed_sites: tuple[str, ...]


@dataclass(frozen=True)
class Source:
    id: str
    source_system: str
    case_id: str
    site: str
    logical_id: str
    revision: int
    event_at: str
    recorded_at: str
    roles: tuple[str, ...]
    text: str
    content_sha256: str
    envelope_sha256: str
    record_type: str
    authority: str
    supersedes_id: str | None
    capture: bool

    @property
    def event_time(self) -> datetime:
        return parse_time(self.event_at, "event_at")

    @property
    def recorded_time(self) -> datetime:
        return parse_time(self.recorded_at, "recorded_at")

    @property
    def family(self) -> tuple[str, str, str, str]:
        return self.source_system, self.site, self.case_id, self.logical_id


@dataclass(frozen=True)
class Snapshot:
    fixture_id: str
    current_case_id: str
    default_cutoff: str
    base: tuple[Source, ...]
    captures: dict[str, Source]
    attachments: tuple[dict[str, Any], ...]
    source_file_hashes: dict[str, str]


@dataclass(frozen=True)
class Admitted:
    principal: Principal
    cutoff: str
    capture_id: str | None
    sources: tuple[Source, ...]
    attachments: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Replay:
    current: tuple[Source, ...]
    superseded: tuple[Source, ...]
    conflicted: tuple[Source, ...]
    conflicted_families: tuple[tuple[str, str, str, str], ...]


def _source(row: Any, *, capture: bool) -> Source:
    if not isinstance(row, dict):
        raise SourceError("document_invalid")
    sid = source_id(row.get("id"), "source_id")
    case = source_id(row.get("case_id"), "case_id")
    site = source_id(row.get("site"), "site")
    logical = source_id(row.get("logical_id"), "logical_id")
    system = source_id(row.get("source_system"), "source_system")
    revision = row.get("revision")
    if type(revision) is not int or not 1 <= revision <= 1000:
        raise SourceError("revision_invalid")
    event = row.get("event_at")
    recorded = row.get("recorded_at")
    parse_time(event, "event_at")
    parse_time(recorded, "recorded_at")
    roles = row.get("roles")
    if not isinstance(roles, list) or not roles or len(roles) != len(set(roles)):
        raise SourceError("roles_invalid")
    if any(role not in ("investigator", "reviewer") for role in roles):
        raise SourceError("roles_invalid")
    text = row.get("text")
    if not isinstance(text, str) or not text or len(text.encode("utf-8")) > 20_000:
        raise SourceError("text_invalid")
    raw_hash = digest(text.encode("utf-8"))
    if row.get("content_sha256") != raw_hash:
        raise SourceError("text_hash_mismatch")
    record_type = source_id(row.get("record_type"), "record_type")
    authority = source_id(row.get("authority"), "authority")
    link = row.get("supersedes_id")
    if link is not None:
        link = source_id(link, "supersedes_id")
        if link == sid:
            raise SourceError("self_supersession")
    envelope = {key: row[key] for key in sorted(row)}
    return Source(sid, system, case, site, logical, revision, event, recorded,
                  tuple(roles), text, raw_hash, canonical_hash(envelope),
                  record_type, authority, link, capture)


def load_snapshot(folder: Path) -> Snapshot:
    manifest_path = folder / "source-manifest.json"
    manifest_raw = manifest_path.read_bytes()
    if len(manifest_raw) > 100_000:
        raise SourceError("manifest_budget")
    manifest = json.loads(manifest_raw)
    if manifest.get("fixture_id") != "QUALITY-CHRONOLOGY-v1":
        raise SourceError("fixture_mismatch")
    hashes = manifest.get("source_hashes")
    if not isinstance(hashes, dict):
        raise SourceError("source_hash_manifest_invalid")
    parsed = {}
    for name in ("source-corpus.json", "additional-source-captures.json"):
        expected = hashes.get(name)
        if not isinstance(expected, str) or len(expected) != 64:
            raise SourceError("source_hash_manifest_invalid")
        raw = (folder / name).read_bytes()
        if len(raw) > 2_000_000 or digest(raw) != expected:
            raise SourceError("source_file_hash_mismatch")
        parsed[name] = json.loads(raw)
    corpus = parsed["source-corpus.json"]
    extra = parsed["additional-source-captures.json"]
    if corpus.get("fixture_id") != manifest["fixture_id"] or extra.get("fixture_id") != manifest["fixture_id"]:
        raise SourceError("source_fixture_mismatch")
    base_rows = corpus.get("documents")
    capture_rows = extra.get("captures")
    if not isinstance(base_rows, list) or not isinstance(capture_rows, list):
        raise SourceError("source_rows_invalid")
    if len(base_rows) > 100 or len(capture_rows) > 20:
        raise SourceError("source_count_budget")
    base = tuple(_source(row, capture=False) for row in base_rows)
    captures = {row.id: row for row in (_source(x, capture=True) for x in capture_rows)}
    ids = [row.id for row in base] + [row.id for row in captures.values()]
    if len(ids) != len(set(ids)) or len(captures) != len(capture_rows):
        raise SourceError("source_id_duplicate")
    attachments = corpus.get("attachment_manifest")
    if not isinstance(attachments, list) or len(attachments) > 100:
        raise SourceError("attachment_manifest_invalid")
    for attachment in attachments:
        if not isinstance(attachment, dict) or not isinstance(attachment.get("present_in_export"), bool):
            raise SourceError("attachment_manifest_invalid")
        source_id(attachment.get("id"), "attachment_id")
        source_id(attachment.get("referenced_by"), "attachment_reference")
    current_case = source_id(manifest.get("current_case_id"), "current_case_id")
    cutoff = manifest.get("default_cutoff")
    parse_time(cutoff, "cutoff")
    return Snapshot(manifest["fixture_id"], current_case, cutoff, base, captures,
                    tuple(attachments), dict(hashes))


def principal(name: str) -> Principal:
    if not isinstance(name, str):
        raise SourceError("demo_principal_unavailable")
    config = PRINCIPALS.get(name)
    if config is None:
        raise SourceError("demo_principal_unavailable")
    role, sites = config
    return Principal(name, role, sites)


def admit(snapshot: Snapshot, principal_id: str, cutoff: str,
          capture_id: str | None = None) -> Admitted:
    actor = principal(principal_id)
    point = parse_time(cutoff, "cutoff")
    capture = snapshot.captures.get(capture_id) if capture_id is not None else None
    if capture_id is not None and (
        capture is None or capture.site not in actor.allowed_sites
        or actor.role not in capture.roles or capture.recorded_time > point
    ):
        raise SourceError("capture_unavailable")
    rows = list(snapshot.base)
    if capture is not None:
        rows.append(capture)
    visible = tuple(row for row in rows
                    if row.site in actor.allowed_sites and actor.role in row.roles
                    and row.recorded_time <= point)
    ids = {row.id for row in visible}
    attachments = tuple(item for item in snapshot.attachments
                        if item["referenced_by"] in ids)
    return Admitted(actor, cutoff, capture_id, visible, attachments)


def replay(visible: tuple[Source, ...]) -> Replay:
    groups: dict[tuple[str, str, str, str], list[Source]] = {}
    for row in visible:
        groups.setdefault(row.family, []).append(row)
    current: list[Source] = []
    superseded: list[Source] = []
    conflicted: list[Source] = []
    families = []
    for family, rows in groups.items():
        revisions: dict[int, list[Source]] = {}
        for row in rows:
            revisions.setdefault(row.revision, []).append(row)
        if any(len({r.envelope_sha256 for r in same}) > 1 for same in revisions.values()):
            families.append(family)
            conflicted.extend(rows)
            continue
        unique = [min(same, key=lambda r: (r.recorded_time, r.id))
                  for same in revisions.values()]
        by_id = {r.id: r for r in unique}
        followed = set()
        malformed = False
        for row in unique:
            if row.supersedes_id is None:
                continue
            predecessor = by_id.get(row.supersedes_id)
            if predecessor is None or predecessor.revision >= row.revision:
                malformed = True
                break
            followed.add(predecessor.id)
        if malformed or len(unique) - len(followed) != 1:
            families.append(family)
            conflicted.extend(rows)
            continue
        current.extend(r for r in unique if r.id not in followed)
        superseded.extend(r for r in unique if r.id in followed)
    current.sort(key=lambda r: (r.event_time, r.recorded_time, r.id))
    superseded.sort(key=lambda r: (r.event_time, r.revision, r.id))
    conflicted.sort(key=lambda r: (r.event_time, r.revision, r.id))
    return Replay(tuple(current), tuple(superseded), tuple(conflicted),
                  tuple(sorted(families)))


def exact_span(row: Source, quote: str) -> tuple[int, int]:
    if not isinstance(quote, str) or not quote:
        raise SourceError("quote_invalid")
    index = row.text.find(quote)
    if index < 0:
        raise SourceError("quote_not_in_source")
    if row.text.find(quote, index + 1) >= 0:
        raise SourceError("quote_ambiguous")
    return index, index + len(quote)


def packet_fingerprint(snapshot: Snapshot, admitted: Admitted, selected: tuple[Source, ...],
                       proposal_hash: str, question_hash: str) -> str:
    return canonical_hash({
        "version": RULE_VERSION,
        "fixture": snapshot.fixture_id,
        "source_files": snapshot.source_file_hashes,
        "principal": admitted.principal.principal_id,
        "role": admitted.principal.role,
        "sites": admitted.principal.allowed_sites,
        "cutoff": parse_time(admitted.cutoff, "cutoff").isoformat(),
        "capture": admitted.capture_id,
        "sources": [(r.id, r.content_sha256, r.envelope_sha256) for r in selected],
        "proposal": proposal_hash,
        "questions": question_hash,
    })
