# Decisions and Current State

## Current implementation and latest full run (2026-10-25)

- `code/main.py` resolves intent in English, Portuguese, Spanish, French, Japanese, and Korean; deletion and negation verbs are stem matched. Enabled flow states accept `true`, `1`, `yes`, `on`, and `enabled`. Backup rows are deduplicated by source and resource at the latest capture time, and `restore_allowed=false` is compliant.
- Intent regression results: 32/32 public sample statuses, 30/30 intent-gate rows, 3/3 extra cases, and 37/37 affirmative "no longer" requests classified as DELETE. Full intent count: 508 DELETE, 10 NOT_DELETION, 0 UNRESOLVED.
- Full output run: 518 rows; 196 COMPLETE, 312 INCOMPLETE, 10 NOT_APPLICABLE. The latest run recorded 0 unresolved-intent fallbacks in `evaluation/unresolved_intent_flags.csv`; if any remain, the writer audits them as deletion requests and records their case IDs in that file.
- No non-English request remained non-DELETE. Language/template counts after replacing case-specific emails, names, IDs, phone numbers, and numeric tokens: English 370, French 1, Japanese 1, Korean 1, Portuguese 1, Spanish 1.

## Historical baseline (superseded)

- `code/main.py` is a no-LLM keyword intent baseline. It reads the request and supporting CSVs, but only uses `request_text` to decide status: a deletion cue yields `INCOMPLETE` with `steps_json=[]`; otherwise it yields `NOT_APPLICABLE` with `[]`. It never emits `COMPLETE` and does not inspect case evidence, identity history, policy, activity, or audit-time cutoffs.
- `code/validate_output.py` checks 518 rows, header order, unique sorted case IDs, allowed statuses, valid JSON arrays, `NOT_APPLICABLE` emptiness, and consecutive step numbers. It does not yet check exact case-ID coverage, exact step keys, allowed phase/operation/state pairs, phase order, evidence existence/cutoff, or semantic completeness.
- `code/eval.py` scores the baseline's binary intent function against a hand-written 30-case intent gate. It scored 22/30 (73.3%). Keep this only as a small intent regression gate; it is not full-task evaluation.
- A read-only in-memory run of the same baseline logic on the 32 public sample requests scored:
  - Status accuracy: 16/32 (50.0%). Confusion matrix (rows=gold, columns=prediction):

    | Gold status | Predicted COMPLETE | Predicted INCOMPLETE | Predicted NOT_APPLICABLE |
    |---|---:|---:|---:|
    | COMPLETE | 0 | 6 | 4 |
    | INCOMPLETE | 0 | 16 | 6 |
    | NOT_APPLICABLE | 0 | 0 | 0 |

  - Step-level exact reference steps reproduced: 0/193 (0%).
  - Field-level matches in reference step slots: 0/1,351 (0%).
  - Exact ordered sequence accuracy: 0/32 (0%).

  The sample set has 22 `INCOMPLETE`, 10 `COMPLETE`, and no `NOT_APPLICABLE` rows, so it cannot measure that status. The baseline predicted no steps for every case.

## Superseded approach

The intent-only baseline is superseded as a solution approach because the task audits identity history, policy-governed records, global evidence, timestamps, active data flows, restore risks, and ordered remediation. Its keyword decision cannot establish any of those facts. The 30-case set is superseded as the primary evaluation; retain it only as a small intent regression gate because the public samples contain no NOT_APPLICABLE cases. Treat its ambiguous examples as provisional labels.

## Planned architecture (not implemented)

### Tier 1 - output contract and strict validation

- Load all 518 input cases and write exactly one row for each exact `case_id`, sorted ascending, with the required columns and valid JSON arrays.
- Validate the exact case-ID set, row count, column order, allowed statuses, exact seven step fields, consecutive numbering, allowed phase/operation/state combinations, and phase order.
- Validate `NOT_APPLICABLE` has `[]`; `COMPLETE` contains only verification steps; `INCOMPLETE` has grounded findings, remediation and future verification. Findings and `COMPLETE` verification must cite an existing `file_id`, `activity_id` or `audit_id`; remediation and future verification for `INCOMPLETE` must use `evidence_id=""`. Resolve each cited ID in its source and reject it if its capture/event time is after `audit_at`.

### Tier 2 - request intent

- Use deterministic multilingual and negation-aware rules for clear deletion, access, correction, export, and marketing requests.
- Use an LLM only to classify ambiguous request text into a fixed schema with a short supporting span. Validate the schema and ignore instructions embedded in the request as untrusted content.
- With no API key or an LLM error, run deterministic rules and keep unresolved intent visible in diagnostics; never let model availability prevent a local run.

### Tier 3 - evidence-backed deletion audit

- Use only participant-facing inputs; no organizer truth, golden labels, hardcoded case families or post-cutoff evidence. Join request email to current identity and historical email/phone/hash values, then resolve grounded resource IDs.
- Parse CSV, JSON, logs, SQL and SQLite snapshots deterministically; compare primary and replica state at the cutoff. Extract PDF text with `pypdf`; use an LLM only when unstructured text or screenshot content must be converted into validated facts.
- Cache extracted facts by file hash, extractor/model version and schema. Keep evidence IDs, source timestamps and extracted spans attached to each fact. On LLM/API failure, use deterministic extraction and mark unreadable visual-only evidence unresolved; do not invent facts or citations.

### Tier 4 - policy verdict and ordered steps

- Apply `deletion_rules.csv` to every linked copy, retained record, tombstone, data flow and restore path. A tombstone retains only stable `user_id`; remove name, email, phone and email hash.
- `COMPLETE` requires all required treatments, no active sync/import/restore path, retained records with only permitted identifiers, and required retained records still present.
- The sample-output audit found zero violations of the problem statement's operation-table ordering across all 32 cases. For example, `case_11` disables its flow before delete/redact/anonymize steps; `case_09` blocks restore before verification. No sample has a dependency where a downstream and source record require the same operation, so that tie-break remains untested.
- Proposed deterministic ordering: enforce required dependency edges first (disable/block before dependent changes; downstream before source where evidenced), then use the problem statement's operation-table rank, `system_id`, and `resource_id` as stable tie-breakers for otherwise independent steps. Recheck this against samples and document any conflict before implementation.

## Evaluation, usage and packaging plan

- Score against all 32 public sample rows: case/status accuracy, exact step and field matches, and exact ordered sequence accuracy. Add at least three clearly labeled team-created audit cases; retain the 30-case intent set only as a narrow gate.
- Write `evaluation/evaluation_report.md` and `evaluation/usage_report.md` in the top-level `evaluation/` directory. The usage report must come from the same final full run that produced root `output.csv`, and include per-call and aggregate model/token/cost counts.
- Plan extraction at artifact level, not once per case: parse structured files locally, cache by content hash, and batch only ambiguous requests or visual/text evidence facts. Initial quota: at most 26 LLM calls for the 518-case run (up to 21 batches of 25 request texts plus 5 batches of visual artifacts), 140k input tokens and 20k output tokens; run up to five calls concurrently with a 10-second timeout. Target about 30 seconds for local parsing plus up to 90 seconds for model work; API failure falls back locally. The dollar cap remains unset until a provider/model and current prices are selected; report actual cost from the final run.
- Package only runnable source, prompts/configuration, README, and evaluation reports. Exclude `dataset/`, `.venv/`, caches, nested archives and secrets. Add a packaging script and ignore `.venv/`, `.env`, and cache directories.

## Cut list

- No autonomous tool-using agent, vector database, embeddings, external search, fine-tuning, model voting, or hand-coded case families: these add moving parts without improving grounded decisions over the supplied finite evidence.
- No LLM-generated status verdicts, remediation sequences or unsupported citations; deterministic code owns policy, time, state and ordering.
- No LLM calls for structured CSV/JSON/SQL or routine log parsing; reserve model calls for genuinely ambiguous intent or unstructured evidence extraction.
- No network-dependent run path or secret requirement; local parsing and validation must still run without an API key.

## 30-second explanation

“Python links each request to identity history and the supplied evidence, applies the policy at `audit_at`, and validates the ordered CSV steps. An LLM may extract typed facts from ambiguous text or visual evidence; deterministic code decides status and remediation. Without an API key, local parsers still run and flag evidence they cannot read.”

