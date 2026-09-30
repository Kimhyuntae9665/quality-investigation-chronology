"""One development-only P10 Qwen request. No evaluator access or automatic retry."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TOOLING = Path.home() / "ax-lab" / "artifacts" / "p06-tokenizer-tooling"
if TOOLING.is_dir():
    sys.path.insert(0, str(TOOLING))
from quality_queue.domain import canonical_hash, load_snapshot
from quality_queue.model import admitted_input, request_payload, validate_proposal, ProposalError
from quality_queue.tokenizer import load_tokenizer
from quality_queue import inference_guard as guard

DATA = ROOT / "data" / "packet-v1"
OUT = ROOT / "artifacts" / "model-dev-v1"
BASE = "http://127.0.0.1:11434"
CUTOFF = "2026-09-30T10:00:00+09:00"


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_new(name: str, value):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def post(endpoint: str, payload: dict, timeout: int = 30):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(BASE + endpoint, data=raw, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def get(endpoint: str, timeout: int = 10):
    with urllib.request.urlopen(BASE + endpoint, timeout=timeout) as response:
        return json.load(response)


class AmbiguousTransportError(RuntimeError):
    """Request may still be active on the server; require shared timeout barrier."""


def bounded_chat_bytes(payload: dict, *, deadline_s: int, max_bytes: int) -> bytes:
    request_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/chat", data=request_bytes,
                                 headers={"Content-Type": "application/json"})
    if signal.getitimer(signal.ITIMER_REAL)[0] > 0:
        raise RuntimeError("existing_process_deadline")
    old_handler = signal.getsignal(signal.SIGALRM)

    def deadline_expired(_signum, _frame):
        raise TimeoutError("whole_request_deadline")

    signal.signal(signal.SIGALRM, deadline_expired)
    signal.setitimer(signal.ITIMER_REAL, deadline_s)
    try:
        try:
            with urllib.request.urlopen(req, timeout=min(10, deadline_s)) as response:
                declared_text = response.headers.get("Content-Length")
                declared = int(declared_text) if declared_text is not None else None
                if declared is not None and (declared < 0 or declared > max_bytes):
                    raise ValueError("response_byte_budget")
                chunks = []
                total = 0
                while True:
                    chunk = response.read(min(16_384, max_bytes - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("response_byte_budget")
                    chunks.append(chunk)
                if declared is not None and total != declared:
                    raise ValueError("response_length_mismatch")
                return b"".join(chunks)
        except urllib.error.HTTPError:
            # A completed HTTP error response is recorded separately.
            raise
        except BaseException as error:
            # Includes short reads, connection resets, deadline and interrupts.
            raise AmbiguousTransportError(type(error).__name__ + ": " + str(error)[:300]) from error
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def resources():
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10)
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemAvailable:", "MemTotal:")):
            key, value = line.split(":", 1)
            mem[key] = int(value.strip().split()[0])
    return {"gpu_csv_mib_percent": gpu.stdout.strip(), "meminfo_kib": mem}


def payload_and_input():
    snapshot = load_snapshot(DATA)
    model_input = admitted_input(snapshot, "demo-investigator-a", CUTOFF)
    payload = request_payload(model_input)
    return snapshot, model_input, payload


def acquire():
    lease = guard._open_inference_lease()
    try:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        guard._check_timeout_barrier()
        return lease
    except Exception:
        lease.close()
        raise


def release(lease):
    if lease in guard._timeout_guard_leases:
        # A failed barrier write must keep the OS lease in this process.
        while True:
            time.sleep(30)
    lease.close()


def preflight():
    if (OUT / "preflight.json").exists() or (OUT / "attempt-started.json").exists():
        raise RuntimeError("preflight_or_attempt_already_exists")
    lease = acquire()
    try:
        snapshot, model_input, payload = payload_and_input()
        version = get("/api/version")
        tags = get("/api/tags")
        matching = [row for row in tags.get("models", []) if row.get("name") == payload["model"]]
        if len(matching) != 1:
            raise RuntimeError("model_tag_unavailable")
        shown = post("/api/show", {"model": payload["model"]})
        template = shown.get("template")
        if not isinstance(template, str) or not template:
            raise RuntimeError("model_template_unavailable")
        template_hash = hashlib.sha256(template.encode()).hexdigest()
        tokenizer = load_tokenizer()
        render_payload = {**payload, "_debug_render_only": True}
        started = time.monotonic()
        try:
            rendered_http = bounded_chat_bytes(render_payload, deadline_s=75, max_bytes=2_000_000)
        except urllib.error.HTTPError as error:
            raise RuntimeError("render_http_" + str(error.code)) from error
        except AmbiguousTransportError:
            guard._latch_timeout(lease)
            raise
        try:
            debug = json.loads(rendered_http)
        except json.JSONDecodeError:
            guard._latch_timeout(lease)
            raise RuntimeError("render_response_invalid_json_completion_uncertain")
        rendered = debug.get("_debug_info", {}).get("rendered_template")
        if not isinstance(rendered, str) or not rendered:
            raise RuntimeError("render_only_missing_template")
        token = tokenizer.count_rendered_prompt(rendered)
        context = payload["options"]["num_ctx"]
        reserve = payload["options"]["num_predict"] + 64
        receipt = {
            "created_at_utc": now(),
            "development_only": True, "generation_requests": 0,
            "ollama_version": version.get("version"),
            "model_tag": payload["model"], "model_tag_digest": matching[0].get("digest"),
            "model_layer_digest": tokenizer.provenance["model_manifest_layer_digest"],
            "gguf_metadata_sha256": tokenizer.provenance["metadata_sha256"],
            "template_sha256": template_hash,
            "input_hash": model_input["input_hash"],
            "source_file_hashes": snapshot.source_file_hashes,
            "source_ids": [x["source_id"] for x in model_input["sources"]],
            "request_sha256": canonical_hash(payload),
            "schema_sha256": canonical_hash(payload["format"]),
            "rendered_prompt_sha256": token["rendered_prompt_sha256"],
            "rendered_prompt_utf8_bytes": token["prompt_utf8_bytes"],
            "input_tokens_cpu": token["input_tokens"],
            "output_plus_headroom_reserve": reserve,
            "context_limit": context,
            "fits": token["input_tokens"] + reserve <= context,
            "render_wall_s": round(time.monotonic() - started, 3),
            "runner_token_parity_proven": False,
            "resources_after_render": resources(),
        }
        atomic_new("preflight.json", receipt)
        print(json.dumps({"preflight": str(OUT / "preflight.json"),
                          "input_tokens": receipt["input_tokens_cpu"],
                          "reserve": reserve, "context": context,
                          "fits": receipt["fits"],
                          "render_wall_s": receipt["render_wall_s"],
                          "source_ids": receipt["source_ids"],
                          "model_digest": receipt["model_tag_digest"],
                          "template_sha256": template_hash}, ensure_ascii=False))
    finally:
        release(lease)


def development_call():
    preflight_path = OUT / "preflight.json"
    if not preflight_path.exists():
        raise RuntimeError("preflight_required")
    if (OUT / "attempt-started.json").exists():
        raise RuntimeError("attempt_already_started_no_retry")
    preflight_receipt = json.loads(preflight_path.read_text())
    if not preflight_receipt.get("fits"):
        raise RuntimeError("context_not_fit")
    lease = acquire()
    try:
        snapshot, model_input, payload = payload_and_input()
        if preflight_receipt["input_hash"] != model_input["input_hash"]:
            raise RuntimeError("source_or_scope_changed")
        if preflight_receipt["request_sha256"] != canonical_hash(payload):
            raise RuntimeError("request_changed_after_preflight")
        version = get("/api/version")
        shown = post("/api/show", {"model": payload["model"]})
        template_hash = hashlib.sha256(shown["template"].encode()).hexdigest()
        if template_hash != preflight_receipt["template_sha256"]:
            raise RuntimeError("template_changed_after_preflight")
        tags = get("/api/tags")
        matching = [row for row in tags.get("models", []) if row.get("name") == payload["model"]]
        if len(matching) != 1 or matching[0].get("digest") != preflight_receipt["model_tag_digest"]:
            raise RuntimeError("model_digest_changed_after_preflight")
        prior = resources()
        atomic_new("attempt-started.json", {
            "started_at_utc": now(), "request_sha256": canonical_hash(payload),
            "model_tag_digest": preflight_receipt["model_tag_digest"],
            "template_sha256": template_hash, "resources_before": prior,
            "http_request_count_planned": 1})
        started = time.monotonic()
        try:
            raw_http = bounded_chat_bytes(payload, deadline_s=120, max_bytes=1_000_000)
        except urllib.error.HTTPError as error:
            atomic_new("http-error.json", {"at": now(), "status": error.code,
                                            "body_not_read": "avoid unbounded error-body read"})
            raise
        except AmbiguousTransportError as error:
            guard._latch_timeout(lease)
            atomic_new("transport-error.json", {"at": now(), "type": type(error).__name__,
                                                 "message": str(error)[:400],
                                                 "timeout_barrier": True})
            raise
        wall_s = round(time.monotonic() - started, 3)
        fd = os.open(OUT / "raw-http-response.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, raw_http)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            response = json.loads(raw_http)
        except json.JSONDecodeError as error:
            guard._latch_timeout(lease)
            atomic_new("outcome.json", {"at": now(), "request_wall_s": wall_s,
                                        "structural_status": "server_response_invalid_json",
                                        "timeout_barrier": True})
            raise
        atomic_new("raw-response.json", response)
        after = resources()
        message = response.get("message") if isinstance(response, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        thinking = message.get("thinking") if isinstance(message, dict) else None
        outcome = {"at": now(), "request_wall_s": wall_s,
                   "http_request_count": 1,
                   "done": response.get("done"),
                   "done_reason": response.get("done_reason"),
                   "ollama_metrics": {key: response.get(key) for key in (
                       "total_duration", "load_duration", "prompt_eval_count",
                       "prompt_eval_duration", "eval_count", "eval_duration")},
                   "content_chars": len(content) if isinstance(content, str) else None,
                   "thinking_chars": len(thinking) if isinstance(thinking, str) else None,
                   "resources_after": after,
                   "structural_status": None, "meaningful_sample_fields": False,
                   "correct_4_of_50": False}
        if not response.get("done") or response.get("done_reason") == "length":
            outcome["structural_status"] = "incomplete_generation"
        elif not isinstance(content, str):
            outcome["structural_status"] = "missing_content"
        else:
            try:
                checked = validate_proposal(model_input, content)
                outcome["structural_status"] = "valid" if checked["complete_for_development_case"] else checked["failure"]
                outcome["proposal_check"] = checked
                outcome["meaningful_sample_fields"] = checked["complete_for_development_case"]
                outcome["correct_4_of_50"] = checked["observed_values"] == {
                    "sample_wrong": "4", "sample_inspected": "50"}
            except ProposalError as error:
                outcome["structural_status"] = str(error)
        atomic_new("outcome.json", outcome)
        print(json.dumps({"outcome": str(OUT / "outcome.json"),
                          "wall_s": wall_s, "done_reason": outcome["done_reason"],
                          "structural_status": outcome["structural_status"],
                          "meaningful_sample_fields": outcome["meaningful_sample_fields"],
                          "correct_4_of_50": outcome["correct_4_of_50"],
                          "thinking_chars": outcome["thinking_chars"],
                          "content_chars": outcome["content_chars"],
                          "prompt_eval_count": outcome["ollama_metrics"]["prompt_eval_count"],
                          "eval_count": outcome["ollama_metrics"]["eval_count"]}, ensure_ascii=False))
    finally:
        release(lease)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("preflight", "run"))
    phase = parser.parse_args().phase
    preflight() if phase == "preflight" else development_call()
