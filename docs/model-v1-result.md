# P10 Qwen development case v1 — measured failure

This is **one development case**, not the nine-case evaluator or a model quality score. The evaluator/oracle was not opened or passed to the model. Exact synthetic request/response and structured receipts are in [evidence/model-dev-v1](../evidence/model-dev-v1/).

## Fixed input and measured fit

- Scope: PLANT-A demo investigator, availability cutoff 2026-09-30 10:00 +09:00; five admitted effective current-case records QDOC-004, QDOC-002, QDOC-003, QDOC-005, QDOC-006. No predecessor QDOC-001, historical cases, denied PLANT-B row, later conclusion, or evaluator material entered the request.
- Existing local model: qwen3:4b Q4_K_M, tag digest 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7; Ollama 0.17.7; installed template SHA-256 2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9. No model download or server configuration change.
- Debug render only, with installed GGUF tokenizer reconstructed on CPU: 1,267 input tokens; 320 requested output tokens plus 64 headroom = 1,651 of 4,096 available. The actual response's prompt_eval_count was 1,267. That field is **not proof of KV cache reuse**. Debug render used zero generation requests.
- The single generation request used think:false, truncate:false, shift:false, stream:false, temperature 0, one slot and the shared lock. The server returned done=true, done_reason=stop.

## Output and outcome

The response was structurally parseable JSON but contained response_state=abstained, observations=[], questions=[]. Its abstain_reason itself quoted QDOC-002's exact phrase “four incorrectly labelled units among 50 inspected units,” then incorrectly argued that this admitted current correction was not a current fact. QDOC-002 explicitly supersedes QDOC-001 and is current at the selected cutoff. Therefore the model missed both required quantities and the evidence question. **Format validity did not become substantive success.**

- Schema valid: yes. Development completeness: no. Structured source-linked observations: 0/2 required fields. Structured source-bound questions: 0/1 required. Correct 4/50: no. Current status interpretation: incorrect. No causal diagnosis was validated.
- Whole request: 5.415 s. Ollama total_duration: 5.413 s; load_duration: 1.684 s; prompt_eval_duration: 0.325 s; eval_count: 201; eval_duration: 2.535 s. Separate thinking field was absent; the verbose rationale appeared in abstain_reason.
- GPU snapshot before request: 383 MiB used, 7,422 MiB free; immediately after response: 3,556 MiB used, 4,249 MiB free, GPU utilization 88%. These are snapshots, not peak allocation. Later /api/ps listed no loaded model or compute app; shared lease was free and no timeout marker existed.
- No automatic retry or nine-case evaluation followed. A development-only v2 wording clarification is [proposed separately](model-v2-proposal.md).

The server's HTTP completion and a valid JSON shell cannot establish source grounding or correct chronology. This local fictional case does not measure real quality investigation performance.
