# P10 development test and media manifest

- Date: 2026-09-30 UTC; target: remote RTX 4060 host, P10 loopback port 19094.
- Packet: Library quality-chronology-fixtures-v1.zip, 20,394 bytes, SHA-256 1e0eaff74ad92c0f5526eda1a672038371c41b3718c592c88f397ef5854e97bb. Public source files extracted after per-member hash verification. Evaluator-only oracle was not extracted into this project.
- CPU tests: python3 -m unittest discover -s tests -v; 53 tests passed. Covers cutoff admission, explicit correction replay, conflict quarantine, source hashes/quotes, denied site, local receipt, stale receipt and HTTP scope behavior.
- JavaScript: node --check static/app.js passed.
- Browser: installed Google Chrome through Playwright on actual local app. Desktop 1440x900 and mobile 390x844. Verified 09:15 5/50 and no future correction source ID, 10:00 4/50 with old value in correction history, open source, accepted handoff with five open requests, conflict acceptance disabled but return allowed, all three admitted conflict sources openable, review history and export available, changed-note receipt preserved, delayed review pending state released, delayed source read dropped after cutoff switch, and mobile scroll width 390px at 390px viewport. Script: tests/browser_demo.py.
- Captures: artifacts/demo/01-current-desktop.png through 07-current-mobile.png are unaltered screenshots. Fictional source only. No credentials, private host address or real factory data in the app UI.
- Model calls: two locked development Qwen requests, v1 and v2 after generation-free render preflight. V1 failed the required 4/50 and question output; see docs/model-v1-result.md and evidence/model-dev-v1/. No held-out model score or CAG claim. Packet self-validation is not a model/app accuracy score.
- Limits: UI reviewer identity is demo selection, review receipts are process-memory only, no external operational write, and semantic causal validity has not been independently established.

- Actual video: artifacts/demo/workflow.mp4, 10.04 seconds, 1,219,404 bytes. Playwright captured the live Chrome page through the installed system ffmpeg, then converted the recorded stream to H.264; no frames were composited to depict success.
- Delayed review POST followed by a cutoff change was checked in the browser; the old receipt did not appear in the new view.
- Independent read-only review found stale visible content during failed scope reload and malformed POST field-type handling; both were fixed. Browser failed-scope race and HTTP JSON-400 regression now pass.
- Incremental review found ambiguous transport-read/overall-deadline issues in the optional model runner. Fail-closed barrier handling, independent timer and declared-length equality were added; six CPU transport regressions pass. No extra model request was made.

- Bounded v2 development contract: ten additional CPU tests; original v1 response retained. V2 model render/generation and nine evaluator cases have not run. Shared GPU lease was released.

- V2 Qwen development: one generation-free actual-template render (1,671 input + 576 reserve <= 4,096), one 9.062-second generation call. JSON response had five correctly state-linked required assertions but also one history-to-current assertion, an English question, and normalized rather than literal raw number words. Strict acceptance failed. Raw receipt: evidence/model-dev-v2/. The shared lock was free and timeout marker absent after the runner exited. Formal nine-case evaluation remains unrun.

## CPU UI review, 2026-09-30

- 53 Python contract/API tests and Node syntax check passed; actual Chrome scripts tests/browser_keyboard.py, tests/browser_review_regressions.py and tests/browser_demo.py passed. Both browser scripts operate against loopback; review_regressions.py starts and stops its own temporary server.
- A delayed review POST followed by a cutoff change no longer leaves review disabled. Old results are not rendered into the new view. A failed POST directs users to visible history before retrying, because the server outcome may be unknown.
- Demo investigator has no review action; demo reviewer may accept a faithful packet with explicit open questions or return a blocked conflict packet. JSON export is bound to current scope, source and receipt freshness.
- The current inspection row being quarantined makes product context unknown; the UI no longer asserts a product difference without an admitted current value. All three admitted conflicting captures are inspectable with status.
- Four additional unaltered Chrome screenshots in artifacts/ui-review/ show desktop review history, desktop and 390px conflict states, and earlier cutoff after delayed source. At 390px document scroll width measured 390px; computed card prose 15.04px, controls 16px, hints 14.4px.
- Original seven screenshots and video were regenerated on a separate updated loopback server after the actor/action policy change. No model calls were made for this UI pass.
