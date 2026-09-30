# Small quality handoff implementation

## Distinct screen and task

Build a chronology workspace with three connected views: event/recorded-time timeline and correction replay; current-versus-historical case comparison with differences; and a local evidence-request queue. A row/source viewer remains available when a user opens evidence, but the central task is chronology and unresolved-question handoff rather than a second extraction grid.

The first result is a correctly reviewed source-bound handoff at a chosen cutoff. It need not settle the cause or close every evidence question. The UI must keep the investigation state distinct from review state.

## CPU first

1. Load the small base corpus and verify text hashes and the manifest file hashes
2. Apply site/role and inclusive recorded_at cutoff checks in the backend
3. Build the admitted supersession graph, historical correction trace and conflict state
4. Show current source records, qualified source facts and exact sample arithmetic
5. Create source-linked local evidence questions and compare the two eligible historical cases without importing their causes
6. Let a demo reviewer accept or return the current handoff; invalidate a receipt when its bound inputs change
7. Export only authorized current handoff content with gaps, historical references clearly labeled and no operational write

The deterministic baseline is the chronology, typed source checklist, ID-based joins and lexical prior-case retrieval. A model is optional. If used later, evaluate paraphrased assertion/status extraction and supported-question drafting against the baseline. Report schema success, exact supported fields, unsupported assertions, abstention/corrections, latency and observed memory separately. Do not add embeddings, a vector database or multi-agent runtime without a demonstrated problem that requires them.

## State checks

- Replay 09:15, 09:20, 10:00 and 11:05 knowledge snapshots with inclusive availability boundaries
- Preserve corrections and reject contradictory same-revision captures without falling back to superseded facts
- Change a previously accepted observation; the existing receipt becomes stale
- Omit the inspected-unit denominator; no rate may use the lot total in its place
- Deny all sites; every source/detail/search/comparison/export path is empty without hidden-source counts
- Change role or site access after review; current export must reauthorize source access
- Reject unsupported claims even when an existing source ID is cited
- Treat embedded instructions as source text; they cannot change scope, cutoff or review authority
- Preserve a usable deterministic view after model failure

Additional UI tests should verify which chronology point is selected, which source/correction is opened, visible active cutoff/scope, keyboard access, empty states and stale-receipt explanations. These are implementation tests to perform, not results established by this packet.

## Evidence and claims

No local-model score or application pass count is included. The evaluator contains related synthetic scenarios, not an independent external holdout. Do not claim reduced deviations, faster actual investigations, verified root causes, compliance or production readiness. A future productivity comparison must include review/correction time and a suitable human baseline.
