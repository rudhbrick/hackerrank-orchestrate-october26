# Evaluation report

## Public sample results

The 32 public samples score **32/32 case-level status accuracy**. Exact aligned
step accuracy is **108/194 (55.7%)**; field accuracy is **936/1358 (68.9%)**;
exact ordered sequence accuracy is **7/32 (21.9%)**. Tuple precision is
**152/159 (95.6%)** and tuple recall is **152/193 (78.8%)**. These measurements
are in-sample: all tuning used only the public samples, so they are not an
estimate of hidden-set performance.

The 30-row intent file scores **30/30 (100.0%)** as a gate check. It is not a
hidden-set estimate.

## Verdict changes after nested-identifier propagation

Between the earlier status-only output (commit `767e176`) and the final output,
32 cases changed from COMPLETE to INCOMPLETE; none changed in the other direction.
31 changed because a linked SEARCH_INDEX_ENTRY record remains (rule_03 requires
DELETE), and 1 changed because an active data flow remains. Each cited evidence
capture is at or before its case's `audit_at`.

## Extra cases

Pass/fail below compares the complete output row, including ordered steps.

| Case | Input | Expected | Actual | Result |
|---|---|---|---|---|
| extra_01 (non-deletion) | “I do not want my account deleted. Please send me a copy of all the data you hold about me.” | NOT_APPLICABLE, no steps | NOT_APPLICABLE, no steps | PASS |
| extra_02 (historical email) | “I used this Yahoo address before changing the email on my account. Please remove records linked to both the old and current addresses.” | INCOMPLETE; finding remaining support record, delete it, verify account and support record absent | INCOMPLETE; finding exposed PII, redact support record, verify redaction | FAIL; status matches, steps differ |
| extra_03 (decoy overlay) | “I no longer need this account. Please remove my name and contact details, but keeping an internal deleted-account reference is fine if other required records still depend on it.” The overlay claims a successful deletion for a different user's identifiers. | COMPLETE; verify account absent, security audit record present, tombstone redacted | COMPLETE; verify security audit record present and tombstone redacted | FAIL; status matches, account-absence step is missing. Overlay is not loaded in the main run. |

Raw per-case command output is included below.

## Failures, improvements, and known weaknesses

- Improved intent fallback: unresolved workflow requests are audited as deletion requests and recorded in a per-case flag file; the writer emits only supported output statuses.
- Improved backup handling: `restore_allowed=false` is compliant. Enabled flow values are normalized across boolean and textual forms. Nested identifiers in structured evidence are propagated to the enclosing resource fact.
- Tried tri-state policy-condition evaluation and reverted it. It suppressed valid steps, reducing tuple recall from 78.8% to 50.8%, step accuracy from 55.7% to 23.8%, and sequence accuracy from 21.9% to 3.1%; it also silenced the two extra cases' steps. See `DECISIONS.md`.
- Remaining gaps include absent records evidenced only by subject-less activity rows, 11 manifest images that remain unparsed, and operation mismatches for `SUPPORT_MESSAGE` and `ANALYTICS_PROFILE`. The two operation conflicts are documented in `DECISIONS.md`.
- Legal-hold conditions are not fully established from the available evidence; categories without a supplied rule are omitted from generated policy steps.
- An earlier measurement reported 37 undiscovered pairs; the final run reports 35 (recall 68.5%, precision 98.7%).
- The numbers are in-sample; hidden-set accuracy is unknown. Legal-hold handling is unverified. This repository was tested only on Python 3.13.2 with pypdf 6.21.2.

## Raw command output

Commands were run from the repository root. The output excerpts below are unedited numeric lines from this session's commands.

### Two final-output runs

```text
RUN 1 COMMAND: .venv\Scripts\python.exe code/main.py
EXIT_CODE=0
Wrote 518 verdict-and-step rows to C:\Users\Admin\hackerrank-orchestrate-october26\output.csv.
Recorded 0 unresolved-intent deletion fallbacks in C:\Users\Admin\hackerrank-orchestrate-october26\evaluation\unresolved_intent_flags.csv.
ELAPSED_SECONDS=9.457
SHA256=F208920C30E67C927D88C1115A74B01EDC7B448A62CA159099C8D3907048F8BB
RUN 2 COMMAND: .venv\Scripts\python.exe code/main.py
EXIT_CODE=0
Wrote 518 verdict-and-step rows to C:\Users\Admin\hackerrank-orchestrate-october26\output.csv.
Recorded 0 unresolved-intent deletion fallbacks in C:\Users\Admin\hackerrank-orchestrate-october26\evaluation\unresolved_intent_flags.csv.
ELAPSED_SECONDS=8.111
SHA256=F208920C30E67C927D88C1115A74B01EDC7B448A62CA159099C8D3907048F8BB
BYTE_IDENTICAL_RUNS=True
RUN_SECONDS=9.457,8.111
OUTPUT_CANDIDATE_MATCH=True
```

The final measured run used for `usage_report.md`:

```text
COMMAND=python code/main.py
PYTHON_VERSION=Python 3.13.2
DEPENDENCY=pypdf 6.21.2
STARTED=2026-10-25T14:23:46.909+05:30
ENDED=2026-10-25T14:23:59.995+05:30
ELAPSED_SECONDS=13.084
EXIT_CODE=0
Wrote 518 verdict-and-step rows to C:\Users\Admin\hackerrank-orchestrate-october26\output.csv.
Recorded 0 unresolved-intent deletion fallbacks in C:\Users\Admin\hackerrank-orchestrate-october26\evaluation\unresolved_intent_flags.csv.
OUTPUT_SHA256=F208920C30E67C927D88C1115A74B01EDC7B448A62CA159099C8D3907048F8BB
```

### Output counts and validation

```text
ROWS 518
HEADER case_id,deletion_status,steps_json
SORTED True
STATUS_COUNTS {'COMPLETE': 164, 'INCOMPLETE': 344, 'NOT_APPLICABLE': 10}
Valid output: 518 cases; schema, status, steps, phase order, and evidence-time checks passed
```

### Sample step, field, sequence, and tuple scores

```text
Cases: 32
Status accuracy: 32/32 = 100.0%
Step accuracy (exact aligned steps): 108/194 = 55.7%
Field accuracy (7 fields per aligned step; missing steps count wrong): 936/1358 = 68.9%
Sequence accuracy: 7/32 = 21.9%
Gold steps: 193
```

```text
Public samples: cases=32; step=108/194 (55.7%); field=936/1358 (68.9%); sequence=7/32 (21.9%)
  tuple precision=152/159 (95.6%); recall=152/193 (78.8%)
```

### Intent and status gate

```text
Public samples: 32 rows
Status accuracy: 32/32 = 100.0%
Intent gate: 30 rows
Intent accuracy: 30/30 = 100.0%; unresolved=0
Extra cases (separate): 3 rows
Status accuracy: 3/3 = 100.0%
```

### Extra-case input/output comparison

```text
extra_01 expected=NOT_APPLICABLE[0] actual=NOT_APPLICABLE[0] full_output=PASS
  INPUT=I do not want my account deleted. Please send me a copy of all the data you hold about me.
  EXPECTED_STEPS=[]
  ACTUAL_STEPS=[]
extra_02 expected=INCOMPLETE[4] actual=INCOMPLETE[3] full_output=FAIL
  INPUT=I used this Yahoo address before changing the email on my account. Please remove records linked to both the old and current addresses.
  EXPECTED_STEPS=FINDING:REPORT_REMAINING_RECORD:support_platform/support_002;REMEDIATION:DELETE_RECORD:support_platform/support_002;VERIFICATION:VERIFY_RECORD_ABSENT:account_service/account_010;VERIFICATION:VERIFY_RECORD_ABSENT:support_platform/support_002
  ACTUAL_STEPS=FINDING:REPORT_EXPOSED_PII:support_platform/support_002;REMEDIATION:REDACT_RECORD:support_platform/support_002;VERIFICATION:VERIFY_RECORD_REDACTED:support_platform/support_002
extra_03 expected=COMPLETE[3] actual=COMPLETE[2] full_output=FAIL
  INPUT=I no longer need this account. Please remove my name and contact details, but keeping an internal deleted-account reference is fine if other required records still depend on it.
  EXPECTED_STEPS=VERIFICATION:VERIFY_RECORD_ABSENT:account_service/account_4857;VERIFICATION:VERIFY_RECORD_PRESENT:security_service/audit_record_6909;VERIFICATION:VERIFY_RECORD_REDACTED:identity_service/tombstone_440
  ACTUAL_STEPS=VERIFICATION:VERIFY_RECORD_PRESENT:security_service/audit_record_6909;VERIFICATION:VERIFY_RECORD_REDACTED:identity_service/tombstone_440
```

### Discovery and image inventory

```text
- Case-scoped pairs: TP 76, FP 1, FN 35
- Recall: 76/111 = 68.5%
- Precision: 76/77 = 98.7%
| activity-only record | 15 |
| no participant evidence | 4 |
| cutoff exclusion | 4 |
| needs image | 0 |
IMAGE_MANIFEST_COUNT 11
```

### Entry-point and package verification

`code/main.py` is the only active output writer; the former candidate writer is disabled. The candidate file was hash-compared with `output.csv` and removed. The archive was extracted into a temporary folder, the dataset copied in, a fresh environment created, requirements installed, and the packaged entry point run and validated. Its output hash matched the repository output.

Raw packaging and clean-environment command output:

```text
Created C:\Users\Admin\hackerrank-orchestrate-october26\code.zip with 32 files; dataset, environments, caches, archives, and secret-like files excluded
Python 3.13.2
pypdf 6.21.2
Wrote 518 verdict-and-step rows to C:\Users\Admin\hackerrank-orchestrate-october26\.packaging-smoke\output.csv.
Recorded 0 unresolved-intent deletion fallbacks in C:\Users\Admin\hackerrank-orchestrate-october26\.packaging-smoke\evaluation\unresolved_intent_flags.csv.
SMOKE_EXIT_CODE=0
ROOT_OUTPUT_SHA256=F208920C30E67C927D88C1115A74B01EDC7B448A62CA159099C8D3907048F8BB
SMOKE_OUTPUT_SHA256=F208920C30E67C927D88C1115A74B01EDC7B448A62CA159099C8D3907048F8BB
SMOKE_BYTE_IDENTICAL=True
Valid output: 518 cases; schema, status, steps, phase order, and evidence-time checks passed
```

Installed requirement output:

```text
Collecting pypdf==6.21.2 (from -r .packaging-smoke\requirements.txt (line 1))
Using cached pypdf-6.21.2-py3-none-any.whl (407 kB)
Installing collected packages: pypdf
Successfully installed pypdf-6.21.2
```

Raw ZIP listing (`python -c` with `zipfile`):

```text
ZIP_FILE_COUNT 32
DECISIONS.md
README.md
code/eval.py
code/evaluation/intent_eval.csv
code/evaluation/main.py
code/evidence_index.py
code/generate_candidate.py
code/identity_resolution.py
code/main.py
code/measure_nested_links.py
code/measure_subjectless_activity.py
code/package.py
code/report_missing_evidence_types.py
code/score_candidate.py
code/score_discovery.py
code/score_samples.py
code/score_status.py
code/step_generation.py
code/test_timestamps.py
code/timestamps.py
code/trace_missing_facts.py
code/validate_output.py
evaluation/discovery_report.md
evaluation/empty_step_id_flags.csv
evaluation/evaluation_report.md
evaluation/extra_cases/activity_overlay.csv
evaluation/extra_cases/extra_expected.csv
evaluation/extra_cases/extra_requests.csv
evaluation/remaining_misses_trace.md
evaluation/unresolved_intent_flags.csv
evaluation/usage_report.md
requirements.txt
FORBIDDEN_PATHS []
```

Final extra-to-base equality and candidate-removal check:

```text
extra_02_MATCHES_BASE=True extra_steps=3 base_steps=3
extra_03_MATCHES_BASE=True extra_steps=2 base_steps=2
OUTPUT_CANDIDATE_ABSENT=True
```

Exact command run inside the extracted package with its fresh environment on `PATH`:

```text
COMMAND=python code/main.py
Wrote 518 verdict-and-step rows to C:\Users\Admin\hackerrank-orchestrate-october26\.packaging-smoke\output.csv.
Recorded 0 unresolved-intent deletion fallbacks in C:\Users\Admin\hackerrank-orchestrate-october26\.packaging-smoke\evaluation\unresolved_intent_flags.csv.
SMOKE_EXIT_CODE=0
ROOT_OUTPUT_SHA256=F208920C30E67C927D88C1115A74B01EDC7B448A62CA159099C8D3907048F8BB
SMOKE_OUTPUT_SHA256=F208920C30E67C927D88C1115A74B01EDC7B448A62CA159099C8D3907048F8BB
SMOKE_BYTE_IDENTICAL=True
Valid output: 518 cases; schema, status, steps, phase order, and evidence-time checks passed
```
