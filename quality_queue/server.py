from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .baseline import build_packet
from .domain import SourceError, admit, exact_span, load_snapshot, principal, replay
from .review import ReviewError, ReviewStore

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "packet-v1"
STATIC = ROOT / "static"
MAX_BODY = 16_384


class App(ThreadingHTTPServer):
    def __init__(self, port: int):
        self.snapshot = load_snapshot(DATA)
        self.reviews = ReviewStore(self.snapshot)
        self.guard = threading.RLock()
        super().__init__(("127.0.0.1", port), Handler)

    def refresh(self):
        snapshot = load_snapshot(DATA)
        self.snapshot = snapshot
        self.reviews.replace_snapshot(snapshot)
        return snapshot


class Handler(BaseHTTPRequestHandler):
    server: App

    def log_message(self, format, *args):
        # Fictional demo: avoid logging user question text or source content.
        return

    def _host_ok(self) -> bool:
        allowed = {f"127.0.0.1:{self.server.server_port}",
                   f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return host in allowed and (origin is None or origin in
                                    {f"http://{value}" for value in allowed})

    def _headers(self, code: int, content_type: str, length: int):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                         "style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'")
        self.end_headers()

    def _json(self, value, code: int = 200):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
        self._headers(code, "application/json; charset=utf-8", len(raw))
        self.wfile.write(raw)

    def _error(self, code: int, reason: str):
        self._json({"error": reason}, code)

    def _params(self, query: str, allowed: set[str]) -> dict[str, str]:
        parsed = parse_qs(query, keep_blank_values=True, max_num_fields=12)
        if any(key not in allowed or len(values) != 1 or len(values[0]) > 120
               for key, values in parsed.items()):
            raise SourceError("query_parameters_invalid")
        return {key: values[0] for key, values in parsed.items()}

    def _scope(self, params: dict[str, str], snapshot):
        investigator = params.get("investigator", "demo-investigator-a")
        cutoff = params.get("cutoff", snapshot.default_cutoff)
        capture = params.get("capture_id") or None
        return investigator, cutoff, capture

    def do_GET(self):
        if not self._host_ok():
            return self._error(403, "host_or_origin_denied")
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/app.js", "/styles.css"):
            name = "index.html" if path == "/" else path[1:]
            raw = (STATIC / name).read_bytes()
            kind = ("text/html" if name.endswith(".html") else
                    "text/css" if name.endswith(".css") else "text/javascript")
            self._headers(200, kind + "; charset=utf-8", len(raw))
            return self.wfile.write(raw)
        try:
            with self.server.guard:
                snapshot = self.server.refresh()
                if path == "/api/health":
                    return self._json({"ok": True, "fictional": True,
                                       "model_enabled": False,
                                       "fixture_id": snapshot.fixture_id,
                                       "qms_writes": False})
                if path == "/api/view":
                    params = self._params(parsed.query, {"investigator", "cutoff", "capture_id"})
                    investigator, cutoff, capture = self._scope(params, snapshot)
                    return self._json(build_packet(snapshot, investigator, cutoff, capture))
                if path == "/api/scenarios":
                    params = self._params(parsed.query, {"investigator", "cutoff"})
                    investigator, cutoff, _ = self._scope(params, snapshot)
                    actor = principal(investigator)
                    base = admit(snapshot, investigator, cutoff)
                    if not any(row.case_id == snapshot.current_case_id for row in base.sources):
                        return self._json({"captures": []})
                    from .domain import parse_time
                    point = parse_time(cutoff, "cutoff")
                    options = [{"capture_id": row.id, "recorded_at": row.recorded_at,
                                "record_type": row.record_type}
                               for row in snapshot.captures.values()
                               if row.site in actor.allowed_sites and actor.role in row.roles
                               and row.recorded_time <= point]
                    return self._json({"captures": options})
                if path.startswith("/api/source/"):
                    params = self._params(parsed.query, {"investigator", "cutoff", "capture_id", "quote"})
                    investigator, cutoff, capture = self._scope(params, snapshot)
                    target = path[len("/api/source/"):]
                    allowed = admit(snapshot, investigator, cutoff, capture)
                    row = next((item for item in allowed.sources if item.id == target), None)
                    if row is None:
                        return self._error(404, "source_unavailable")
                    viewed = replay(allowed.sources)
                    current = {item.id for item in viewed.current}
                    superseded = {item.id for item in viewed.superseded}
                    state = ("current" if row.id in current else
                             "superseded" if row.id in superseded else "conflicted")
                    out = {"source_id": row.id, "case_id": row.case_id, "site": row.site,
                           "logical_id": row.logical_id, "revision": row.revision,
                           "event_at": row.event_at, "recorded_at": row.recorded_at,
                           "record_type": row.record_type, "source_state": state,
                           "text": row.text, "content_sha256": row.content_sha256,
                           "envelope_sha256": row.envelope_sha256}
                    if "quote" in params:
                        start, end = exact_span(row, params["quote"])
                        out["quote_span"] = [start, end]
                    return self._json(out)
                if path.startswith("/api/export/"):
                    params = self._params(parsed.query, {"investigator", "reviewer", "cutoff", "capture_id"})
                    if "cutoff" not in params:
                        raise ReviewError("active_cutoff_required")
                    investigator = params.get("investigator", "demo-investigator-a")
                    reviewer = params.get("reviewer", "demo-reviewer-a")
                    return self._json(self.server.reviews.export(
                        path[len("/api/export/"):], investigator, reviewer,
                        params["cutoff"], params.get("capture_id") or None))
                if path == "/api/reviews":
                    params = self._params(parsed.query, {"investigator", "reviewer", "cutoff", "capture_id"})
                    if "cutoff" not in params:
                        raise ReviewError("active_cutoff_required")
                    investigator = params.get("investigator", "demo-investigator-a")
                    reviewer = params.get("reviewer", "demo-reviewer-a")
                    return self._json({"reviews": self.server.reviews.list_for(
                        investigator, reviewer, params["cutoff"], params.get("capture_id") or None)})
                return self._error(404, "not_found")
        except (SourceError, ReviewError) as error:
            reason = str(error)
            code = 404 if reason in ("capture_unavailable", "demo_principal_unavailable",
                                     "receipt_unavailable", "review_scope_denied") else 400
            return self._error(code, reason)
        except (OSError, json.JSONDecodeError):
            return self._error(503, "source_snapshot_unavailable")

    def do_POST(self):
        if not self._host_ok():
            return self._error(403, "host_or_origin_denied")
        if urlsplit(self.path).path != "/api/review":
            return self._error(404, "not_found")
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._error(415, "json_required")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= MAX_BODY:
                return self._error(413, "body_budget")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or set(data) - {
                "investigator", "reviewer", "cutoff", "capture_id",
                "packet_fingerprint", "decision", "reviewer_note"
            }:
                raise ReviewError("review_payload_invalid")
            if any(key in data and not isinstance(data[key], str)
                   for key in ("investigator", "reviewer", "cutoff",
                               "packet_fingerprint", "decision", "reviewer_note")):
                raise ReviewError("review_payload_invalid")
            if "capture_id" in data and data["capture_id"] is not None and not isinstance(data["capture_id"], str):
                raise ReviewError("review_payload_invalid")
            with self.server.guard:
                snapshot = self.server.refresh()
                result = self.server.reviews.record(
                    investigator=data.get("investigator", "demo-investigator-a"),
                    reviewer=data.get("reviewer", "demo-reviewer-a"),
                    cutoff=data.get("cutoff", snapshot.default_cutoff),
                    capture_id=data.get("capture_id"),
                    packet_fingerprint=data.get("packet_fingerprint"),
                    decision=data.get("decision"),
                    reviewer_note=data.get("reviewer_note", ""))
                return self._json(result)
        except (ValueError, SourceError, ReviewError) as error:
            return self._error(400, str(error))
        except OSError:
            return self._error(503, "source_snapshot_unavailable")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19094)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("invalid_port")
    App(args.port).serve_forever()


if __name__ == "__main__":
    main()
