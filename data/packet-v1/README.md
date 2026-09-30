# Quality chronology and evidence request fixtures

This small fictional packet supports a quality investigator preparing a handoff. It exercises corrections, historical-case differences, knowledge cutoffs, permission boundaries and requests for missing evidence. All records concern fictional packaging labels and document evidence. It contains no patient data, real factory data, equipment instructions or source-system credentials.

## Files

- source-corpus.json: eleven original short documents and one attachment-availability manifest
- additional-source-captures.json: three mutually exclusive extra observation captures for conflict, correction and missing-denominator tests
- source-manifest.json: source identity, file hashes, fictional dates and model-input boundaries
- public-output-contract.json: typed proposed output and review-state boundaries
- SOURCE-CONTRACT.md: authorization, cutoff, correction, evidence-question and receipt rules
- IMPLEMENTATION.md: CPU-first timeline/queue slice and suggested implementation checks
- evaluation/expected-state-oracle.json: ten source-state scenarios, kept outside model input
- evaluation/README.md: scoring interpretation and independence limits
- evaluation/validation-report.json: completed packet checks only
- PROVENANCE.json and LICENSE.txt: source roles, original authorship and rights
- bundle-manifest.json: file sizes and SHA-256 hashes, excluding itself

## Use

Start with the base corpus, a PLANT-A investigator and September 30, 2026 at 10:00 +09:00. Backend admission runs before any source reaches a model. Additional captures are selected only by the calling scenario. Raw source records remain immutable. Accepted handoffs may openly retain missing evidence and unanswered questions; acceptance does not imply a completed investigation, verified cause, lot release or CAPA closure.

This is a synthetic conformance packet. No model or application was run to produce a performance claim. The expected-state oracle was authored from the sources before model tests. It is separate from runtime sources and must not be indexed, prompted or included in model-readable tools. Related test scenarios are not a blind external benchmark.

## Enterprise reference

Catalent announced Qai on June 16, 2026. Microsoft's September 9 account describes near-complete rollout, documented human validation and read-only access without GMP-record writes. These sources motivate a bounded investigator-support workflow. They do not establish this packet's labels, a local-model score or a measured percentage improvement. No vendor documents, images or private data are bundled.

https://www.catalent.com/news/catalent-launches-qai-to-reimagine-quality-assurance-for-its-manufacturing-services
https://www.microsoft.com/en/customers/story/27171-catalent-azure-openai-in-foundry-models
