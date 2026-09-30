# Quality chronology and evidence request contract

The reader is an investigator preparing a source-bound handoff for a quality reviewer. The prototype preserves chronology, corrections, uncertainty and missing evidence. Its local acceptance state concerns the handoff only. It cannot release a lot, close a CAPA, verify a physical cause, change a quality system or certify compliance.

## Source admission

All source records, cases, times, roles and policies are fictional. The base file holds eleven short documents. Additional captures are mutually exclusive scenario inputs; do not load all three alternatives together. An admitted source must satisfy both the principal's site allowlist and the record's role allowlist, and recorded_at must be less than or equal to the selected cutoff. Authorization applies before retrieval, snippets, counts, comparison, export and model context. An unprivileged response never exposes rejected-source counts, names or existence hints.

recorded_at means source availability in this fictional export. event_at means the event described. They are different: a correction can describe the earlier inspection but become knowable later. A stated future plan may be available now; it remains planned and is not a completed future event. All timestamps carry +09:00. Do not interpret a timezone-naive value without an explicit policy.

Filter scope and availability before following supersession links. Within the same source system, site, case and logical record, an admitted correction explicitly supersedes its stated predecessor. A revision number alone is not an instruction to supersede another logical record. Keep admitted predecessors in correction history, with their original text and hashes; exclude them from current fact extraction. A later inaccessible or unavailable revision must not silently erase the last admitted revision or reveal its existence.

For any identical logical identity plus revision, different text or material envelope fields create a source conflict. No conflicting record becomes current by ingestion order. This conservative fixture blocks the entire conflicting record family from current facts, including values on which the conflicting texts happen to agree. It also blocks acceptance. Superseded predecessors remain historical, not an automatic fallback. This is a declared prototype rule, not an assertion about any vendor system.

## Facts and precedence

Each assertion belongs to a case, topic, source revision and evidence span. Source text SHA-256 covers the exact UTF-8 text; a separate deterministic envelope hash must also bind identity, revision, role/site scope and timing. Preserve both in review receipts. Exact quotation validation uses Unicode codepoint offsets with an exclusive end, not byte positions or JavaScript UTF-16 offsets. Implementations choosing another index convention must convert and declare it consistently.

The current inspection correction replaces the prior inspection quantities; it does not mutate source history. Calculate rate from incorrect units divided by inspected units, never total-lot quantity. Retain the exact fraction. A missing or zero denominator produces no percentage. Do not extrapolate a sample rate to the whole lot.

The later current-case conclusion is a separate assertion with its own source. Once admitted, it changes the displayed cause state from not established to reported conclusion available. Earlier uncertainty stays historical. The application has not independently verified that conclusion. Historical-case causes are attributed to their own cases and never supply the current cause through similarity. An early suspected historical cause remains superseded when a later admitted correction explicitly replaces it.

Keep these states independent: recorded hold versus physical stock coverage; issued material versus installation/use; implemented action versus completed effectiveness evidence; recorded briefing versus individual attendance. Missing evidence means unavailable in the admitted export. It does not establish that an action never happened or a person failed to act.

## Evidence request queue

A local request links a missing fact or qualification to the source that reveals the gap. For example, a missing attendance attachment supports asking for that attachment, not accusing anyone of skipping the briefing. Keep questions in the local workbench. No notification, third-party request or system task is sent by this prototype.

The queue distinguishes open question, supporting evidence present, and reviewer-resolved question. Source evidence may resolve only the issue it supports. Marking a local question resolved cannot create an operational fact or alter a source record. A reported cause may still leave its underlying supporting evidence unavailable.

## Reviewer receipt

The investigator prepares facts and questions; a demo reviewer with the same admitted site scope accepts or returns the handoff. Demo roles are not production authentication or regulated signatures. Acceptance is permitted with explicitly listed open evidence questions, provided every required handoff field is represented as supported, reported or unknown and there is no unresolved source conflict or unsupported assertion. A missing cause is not a reason to invent one or falsely mark the investigation complete.

Bind acceptance to exact source IDs and text/envelope hashes, cutoff, scope, effective revision set, proposed facts/evidence, open-question set, contract/parser/rule/proposal versions, reviewer and time. A material source, cutoff, proposal, question-set or access change makes the current receipt stale. Preserve old receipts. On revocation, block any formerly permitted content from subsequent detail and export paths; historical receipt storage does not grant present access.

An export is a reviewed handoff with explicit gaps. It is never a target-system acknowledgment, CAPA closure, lot disposition or proof of containment. Always state that operational source states are unchanged.

## Model and evaluation boundary

Backend code owns admission, correction precedence, conflicts, arithmetic, quote checking and receipt state. A model may propose source-bound assertions or draft questions. Its empty output, timeout, malformed proposal or unsupported statement must leave the deterministic timeline and queue usable. Gold, scenario expected states, denied records and evaluator-only rejected IDs stay outside prompts, indexes, caches and model tools.
