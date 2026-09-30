# P10 independent review and resolution

A separate read-only reviewer inspected only P10 public project files on 2026-09-30. No GPU request or evaluator/private ZIP access occurred.

1. Medium: after changing scope, the previous packet's numbers, timeline and receipt remained visible while the next read was pending and if it failed. Fixed by clearing all scope-dependent DOM at load start and displaying a failure state. The real-browser regression delays a new read and forces failure; it checks that prior content is not retained.
2. Low: malformed review JSON values such as a reviewer array could cause an uncaught type error instead of a stable 400. Fixed request field-type checks and defense in principal lookup. The HTTP regression posts malformed arrays and verifies JSON 400.

The reviewer found no other concrete issue in admission-before-replay, locked review/export, receipt freshness or the model adapter's source confinement. This is a targeted code review, not certification of security or GMP suitability. The browser role selector is demo identity, not real authentication. Staged public files were independently scanned for credential/private-host markers before publication.

Incremental read-only review of the optional Qwen runner found ambiguous response reads, lack of an independent total deadline and premature EOF risk. The runner now treats uncertain post-dispatch completion as a shared barrier, enforces an independent process timer and verifies declared response length. CPU-only fake-transport tests cover these cases. The v1 generation request had already completed normally before this hardening; its raw receipt was not changed.

A final CPU-only v2 review found that the postvalidator had accepted strings longer than the declared JSON schema limit. It now enforces assertion quote/value and question lengths, with a regression test. The reviewer verified admission-before-replay and the absence of evaluator access; the question usefulness check remains heuristic and is explicitly human-review-required. Full CPU suite: 51 passing. No v2 GPU call occurred.

The final incremental read-only review covered the single v2 runner and six public trace files. Frozen input/request/schema hashes matched preflight, lock/barrier/deadline and exclusive attempt-marker safeguards remained, and no private host/path, credential marker, denied/future source or evaluator reference appeared in those files. The reviewer agreed the v2 result fails because historical QDOC-001 was used for a current-cause assertion and the question was English. This review made no GPU request and is not a production safety or GMP review.
