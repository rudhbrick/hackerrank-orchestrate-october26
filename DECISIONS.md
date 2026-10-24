# Architecture Decisions

## Simple architecture

Use a deterministic Python pipeline, run with `python3 code/main.py`:

1. Read the participant-facing CSVs and evidence manifest.
2. Build indexed identity histories and parse structured evidence (CSV, JSON, SQL, and logs) with ordinary code; extract PDF and screenshot text as needed.
3. Where text is ambiguous or unstructured, ask an LLM only to extract facts or classify request intent into a strict, validated schema. Treat the output as evidence candidates, never as a verdict.
4. Plain code applies `audit_at`, identity matching, deletion rules, and resource/dependency state; constructs ordered findings, remediation, and verification steps; and writes root `output.csv`.
5. Run a local evaluation/validation harness against the public samples and output contract.

The LLM does not choose `deletion_status`, policy actions, citations, remediation order, or final steps. Invalid or unsupported extracted fields are rejected or sent for review; no unsupported fact becomes a finding.

## What is graded

The output is compared with hidden canonical answers. Stated factors are deletion status, identity resolution, remaining records and recreation risks, evidence references, policy application, and completeness/order of `steps_json`. The exact weights and scoring formula are not published. Required evaluation reports cover case/status accuracy, step and field accuracy, sequence accuracy, three or more team-created cases, failures, and improvements.

## Main failure modes

- Missing a historical identifier or matching unrelated global activity.
- Using evidence or identity changes after `audit_at`.
- Treating workflow/activity claims as proof instead of checking resource evidence.
- Missing replica drift, exports, active sync/import jobs, or restore risks.
- Deleting a record that policy requires retained, redacted, anonymized, or kept as a tombstone.
- Incorrect evidence IDs, unsupported findings, or incomplete/incorrectly ordered steps.
- Misclassifying access, correction, export, or marketing opt-out as deletion.
- Invalid CSV/JSON, wrong row count/order, or non-consecutive step numbers.

## Tier plan

### Must-have

- Deterministic input loading, identity history resolution, evidence time filtering, policy application, and output serialization.
- Request-intent classification with a small ruleset, using the LLM only for ambiguous language and only through a strict schema.
- Structured evidence parsing and evidence-backed findings/verification.
- Correct output contract: 518 sorted rows; exact columns and allowed values; valid ordered steps.

### Correctness hazards

- Handle each evidence format sufficiently to find relevant user/resource facts; link by identifiers, hashes, resource/system IDs, and timestamps, not manifest labels.
- Model replica snapshots and process dependencies; disable flows/block restores before dependent record changes, and process downstream copies before their sources where needed.
- Apply every matching deletion rule, including retained records and account tombstones.
- Reject post-cutoff evidence and ground every cited ID in participant-facing data.

### Evaluation harness

- Check row coverage, uniqueness, sort order, exact header, allowed values, JSON schema, consecutive numbering, phase/operation constraints, and evidence-ID validity.
- Compare the 32 public sample outputs and report status, field/step, and sequence metrics where applicable.
- Add at least three team-created cases; record failures and changes. Do not use hidden labels or organizer-only data for prediction or tuning.

### README

- Document setup, dependencies, environment variables (if any), and the exact run command.
- Explain the deterministic pipeline and the LLM's extraction-only boundary.
- State where output and evaluation reports are written and how to run validation.
- Include no secrets or dataset in `code.zip`; place required reports under `code/evaluation/` to match the starter README guidance.

## Cut list

- No autonomous LLM agent or tool-using loop: difficult to audit and unnecessary for the decision logic.
- No LLM-generated final verdicts, steps, or evidence citations: these must be reproducible and checked against policy and sources.
- No vector database, embeddings, or external search: the supplied corpus is finite and can be indexed locally; external facts do not establish the supplied state.
- No online data sources or network-dependent runtime: makes predictions less reproducible and is outside the supplied-evidence basis.
- No fine-tuning, multi-model voting, or elaborate orchestration: high setup and token cost without a clear correctness benefit.
- No hand-coded case families, hidden-label access, organizer truth, or golden-answer shortcuts: prohibited and brittle.
- No broad OCR/vision stack unless ordinary extraction fails on a relevant artifact; use targeted extraction for the supplied screenshots/PDFs.
- No packaging extras beyond runnable code, prompts/configuration, README, and required evaluation reports.

## 30-second explanation

“Python reads the requests, identity history, policy, and evidence. Code matches identities, applies the audit-time cutoff and deletion rules, then builds and validates the ordered CSV steps. An LLM may only turn ambiguous text or documents into typed facts; code checks those facts and makes every final decision.”
