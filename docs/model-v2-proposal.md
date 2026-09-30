# P10 v2 development contract — CPU frozen, model unrun

The original v1 request, response and failed result remain preserved in [evidence/model-dev-v1](../evidence/model-dev-v1/). V1 returned structurally valid JSON but misread the admitted current correction as mere history and left all observations/questions empty. This bounded revision uses only the same development case. No nine-case evaluator output or oracle informed it.

## Exact change

The backend applies site, role and availability cutoff before correction replay. It supplies source_state (current or historical), admitted supersedes_id and superseded_by_id, source hash and timestamps. At 09:15 QDOC-001 is current and QDOC-002 is entirely unavailable; at 10:00 QDOC-002 is current and QDOC-001 is admitted history. A conflict in the current case blocks model input.

The model copies that supplied state. It proposes source assertions for inspection quantities and explicit unknown cause, each with field, status, raw_value, source_id and exact quote. It asks one Korean evidence question linked to a current source. It does not calculate sample or lot rates, infer a current root cause, or close CAPA. The prompt says: “A current correction replaces its historical predecessor. Quantities expressly stated in a current correction are current observations even if that correction mentions an earlier record. Do not abstain from available quantities.” The exact full prompt and JSON schema are in [model_v2.py](../quality_queue/model_v2.py). The prompt contains no QDOC-002, 4/50, development answer or evaluator label.

The schema requires one to eight assertions and one evidence_request. Fields are incorrect_units, inspected_units and current_cause; statuses are current, historical and unknown. Empty assertions are invalid. A lone unknown assertion also fails development completeness. Existing qwen3:4b, Ollama 0.17.7, 4096 context, think:false, truncate:false, shift:false and temperature 0 are retained. The output cap changes from 320 to 512 for the five assertions. Actual v2 template render and token fit remain unmeasured. There will be no debug render or generation until a fresh shared GPU grant.

## One-case acceptance checks

1. Complete JSON/schema, done/stop and a measured context budget with output headroom; HTTP 200 alone cannot pass.
2. Current QDOC-002 contributes four and 50 with current status; historical QDOC-001 contributes Five and 50 with historical status. The source identity and status must match.
3. QDOC-002 supports an unknown current cause and one Korean question about that unknown with a current exact source quote.
4. All source IDs must be admitted. Every quote must occur exactly once in its source. Quantity field and raw number must match the quoted phrase. This is bounded extraction checking, not general semantic verification.
5. The backend alone calculates 4/50 = 2/25 = 8%. Historical 5/50 stays history; total lot 500 is not a sample denominator.
6. Denied-site, future, evaluator-only and CPU typed-answer material stays out of the model request. Changed source or conflict invalidates the proposal.

Ten new [CPU regressions](../tests/test_model_v2.py) cover admission, currentness, empty responses, wrong quantities/status/source/quotes and unsupported questions. All 51 engineering tests pass. The valid_mock value in tests is authored fixture text, not model output. V2 has no actual model result yet; usefulness of a question still needs human review. This one-case development validator is not a scoring oracle for the nine evaluation cases.

Frozen CPU fingerprints before any v2 render/generation: input SHA-256 09e647fc2333bde70facc37332049d6bcdeb535c6f8b9f3962f80e15b5c511d8; request SHA-256 2c75d6be5ee32ed9cbf524f11f86097e984dd88d6fb0f4556a38e9bc35b4d3ef; schema SHA-256 e6cfcd8ee41aaf2f48c5e541b3cdbdeb4bdb46825d1a347f40deb54d240cfa9c. The JSON payload is 6,094 UTF-8 bytes; byte size alone does not prove token fit. Source list: QDOC-004,002,003,005 current; QDOC-001 historical.
