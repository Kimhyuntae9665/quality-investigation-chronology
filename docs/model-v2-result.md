# P10 Qwen v2: one frozen development request, partial extraction and failed acceptance

This is one development case, not the nine-case evaluator. The [v1 failure](model-v1-result.md) and [pre-run v2 contract](model-v2-proposal.md) remain intact. No evaluator/oracle data was opened, and no retry followed. The exact synthetic [v2 request and raw response](../evidence/model-dev-v2/) are preserved.

## Measured fit and execution

- Existing qwen3:4b Q4_K_M on Ollama 0.17.7. Model tag digest 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7; installed template SHA-256 2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9.
- Backend admitted QDOC-004, QDOC-002, QDOC-003, QDOC-005 and QDOC-006 as current, QDOC-001 as historical for PLANT-A at 10:00. Denied site, post-cutoff update, evaluator and typed CPU answer stayed out of the request.
- Generation-free installed-template render plus pinned CPU tokenizer counted 1,671 input tokens. Output cap 512 plus 64 headroom gave 2,247/4,096. Actual prompt_eval_count was also 1,671. This does not prove KV cache reuse.
- Exactly one generation HTTP request with think:false, truncate:false, shift:false, temperature 0 and shared lock. It ended done=true, done_reason=stop. Whole wall 9.062 s; Ollama total_duration 9.061 s; load_duration 1.696 s; prompt_eval_duration 0.437 s; eval_count 443; eval_duration 5.722 s. No separate thinking field was returned.
- GPU snapshots: before request 383 MiB used / 7,422 MiB free; immediately after 3,556 MiB used / 4,249 MiB free, utilization 86%. These are snapshots, not peak VRAM. The runner exited; shared lock was free, timeout marker absent and /api/ps empty. GPU lease released.

## What the model actually proposed

The JSON contained six assertions and one question. Five assertions used admitted, uniquely occurring exact quotes with correct source state: current QDOC-002 four incorrectly labelled units and 50 inspected; historical QDOC-001 Five incorrectly labelled units and 50 inspected; current QDOC-002 explicitly unknown cause. Thus the 4/50 versus 5/50 currentness problem from v1 improved on this single case. The backend alone computes current 4/50 = 2/25 = 8%. The model did not calculate or validate a rate.

The **sixth** assertion assigned current_cause/unknown to historical QDOC-001. Its quote occurs in that source, but the source is historical; the strict postvalidator returned unknown_source_not_current. The question was linked to QDOC-002's current unknown-cause quote, but it was English (“What is the cause of the incorrect labeling for lot L-090?”), contrary to the frozen request for a Korean question. Also, the raw_value strings “4” and “5” normalized the quoted number words “four” and “Five”; they did **not** copy the raw source strings as requested. All six quote strings occurred exactly once in their named admitted sources. Exact occurrence alone did not make the sixth claim current or the question compliant.

**Development acceptance: failed.** The schema-shaped response and five useful source-linked assertions do not override the extra history-to-current assertion, English question or raw-string mismatch. The frozen v2 postvalidator reports the first hard failure; the remaining issues above are a separate CPU audit against the pre-run prompt. This audit did not alter the frozen request or rerun the model. The postvalidator's numeric-equivalence check is looser than the prompt's literal-copy rule, so future protocols should reconcile that before claiming exact raw extraction. No nine-case evaluation or real GMP/quality performance is claimed.
