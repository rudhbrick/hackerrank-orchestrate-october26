# Ghost Data Still Exists

Deterministic deletion audits for the HackerRank Orchestrate October 2026 challenge.
The pipeline reads participant-facing files from `dataset/`, resolves identities,
indexes cutoff-valid evidence, applies the supplied policy, and writes the final CSV.
No API key is needed.

## Requirements

- Python 3.13.2 (the version used for the recorded run)
- Dependencies from `requirements.txt` (`pypdf==6.21.2`)
- A checkout with `dataset/` present

## Setup and run

### Windows PowerShell

```powershell
py -3.13 -m venv .venv
$env:Path = "$PWD\.venv\Scripts;$env:Path"
python -m pip install -r requirements.txt
python code/main.py
python code/validate_output.py
```

### macOS / Linux

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python code/main.py
python code/validate_output.py
```

`python code/main.py` is the sole output-generation entry point. It reads
`dataset/deletion_requests.csv` and supporting files, runs verdict and step
generation, and writes `output.csv` in the repository root. It sorts rows by
`case_id` and writes exactly one row per request.

## Output contract

The CSV header is exactly:

```text
case_id,deletion_status,steps_json
```

The output has 518 data rows. Status is `COMPLETE`, `INCOMPLETE`, or
`NOT_APPLICABLE`. `steps_json` is a JSON array of ordered steps with consecutive
`step_no` values. `NOT_APPLICABLE` rows have an empty array. Evidence references
are cutoff-checked against each case's `audit_at`.

## Layout

- `code/main.py` — single generation entry point and deterministic verdict logic
- `code/evidence_index.py`, `code/identity_resolution.py` — local evidence and identity parsing
- `code/step_generation.py` — policy-based finding, remediation, and verification steps
- `code/validate_output.py` — strict structure, ordering, and evidence-time validator
- `code/score_samples.py`, `code/score_candidate.py`, `code/score_status.py` — public sample, tuple, status, and intent-gate scoring
- `code/score_discovery.py` — public sample resource-discovery measurement
- `code/eval.py` — intent-gate evaluator
- `code/package.py` — builds `code.zip` without dataset, caches, environments, secrets, or nested archives
- `dataset/` — participant-facing inputs and evidence (provided separately)
- `evaluation/` — public discovery report, extra cases, run reports, and flags
- `output.csv` — generated final submission file

## Evaluation commands

Run from the repository root with the environment active:

```bash
python code/score_samples.py
python code/score_candidate.py
python code/score_status.py
python code/score_discovery.py
python code/eval.py
python code/package.py
```

On Windows, prepend `.venv\Scripts` to `PATH` as shown above if PowerShell
script activation is restricted by the machine policy.

The full run metrics and deterministic usage summary are in
`evaluation/evaluation_report.md` and `evaluation/usage_report.md`.
