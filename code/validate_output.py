"""Strict structural and evidence-reference validation for output.csv."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
OUTPUT = ROOT / "output.csv"
HEADER = ["case_id", "deletion_status", "steps_json"]
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
STEP_FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
PHASES = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
ALLOWED = {
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def evidence_index() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for filename, id_field, time_field in (
        ("evidence_files.csv", "file_id", "captured_at"),
        ("system_activity.csv", "activity_id", "event_time"),
        ("user_audit_log.csv", "audit_id", "event_time"),
    ):
        for row in read_csv(DATASET / filename):
            key = row[id_field]
            if key in result:
                raise ValueError(f"Duplicate evidence identifier: {key}")
            result[key] = {"time": row[time_field]}
    return result


def validate() -> int:
    requests = read_csv(DATASET / "deletion_requests.csv")
    expected_ids = sorted(row["case_id"] for row in requests)
    if len(expected_ids) != 518 or len(set(expected_ids)) != 518:
        raise ValueError("deletion_requests.csv must contain exactly 518 unique cases")
    with OUTPUT.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != HEADER:
            raise ValueError(f"Expected columns {HEADER!r} in order; got {reader.fieldnames!r}")
        rows = list(reader)
    if len(rows) != 518:
        raise ValueError(f"Expected exactly 518 output rows; found {len(rows)}")
    ids = [row["case_id"] for row in rows]
    if ids != expected_ids:
        raise ValueError("Output must contain each request case_id exactly once, sorted ascending")
    requests_by_id = {row["case_id"]: row for row in requests}
    known_evidence = evidence_index()

    for line_no, row in enumerate(rows, start=2):
        status = row["deletion_status"]
        if status not in STATUSES:
            raise ValueError(f"Line {line_no}: invalid deletion_status {status!r}")
        try:
            steps = json.loads(row["steps_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Line {line_no}: steps_json is invalid JSON: {exc}") from exc
        if not isinstance(steps, list):
            raise ValueError(f"Line {line_no}: steps_json must be an array")
        if status == "NOT_APPLICABLE" and steps:
            raise ValueError(f"Line {line_no}: NOT_APPLICABLE requires []")
        if status == "COMPLETE" and (not steps or any(not isinstance(s, dict) or s.get("phase") != "VERIFICATION" for s in steps)):
            raise ValueError(f"Line {line_no}: COMPLETE requires verification-only steps")

        last_phase = -1
        audit_at = requests_by_id[row["case_id"]]["audit_at"]
        for expected_no, step in enumerate(steps, start=1):
            if not isinstance(step, dict) or set(step) != STEP_FIELDS:
                raise ValueError(f"Line {line_no}, step {expected_no}: step must have exactly {sorted(STEP_FIELDS)}")
            if type(step["step_no"]) is not int or step["step_no"] != expected_no:
                raise ValueError(f"Line {line_no}: step_no must be consecutive integers from 1")
            if any(not isinstance(step[field], str) for field in STEP_FIELDS - {"step_no"}):
                raise ValueError(f"Line {line_no}, step {expected_no}: all step fields except step_no must be strings")
            combo = (step["phase"], step["operation"], step["state"])
            if combo not in ALLOWED:
                raise ValueError(f"Line {line_no}, step {expected_no}: disallowed phase/operation/state {combo!r}")
            phase_order = PHASES[step["phase"]]
            if phase_order < last_phase:
                raise ValueError(f"Line {line_no}: phases must be ordered FINDING, REMEDIATION, VERIFICATION")
            last_phase = phase_order

            evidence_id = step["evidence_id"]
            requires_evidence = step["phase"] == "FINDING" or status == "COMPLETE"
            if requires_evidence and not evidence_id:
                raise ValueError(f"Line {line_no}, step {expected_no}: this step requires evidence_id")
            if status == "INCOMPLETE" and step["phase"] != "FINDING" and evidence_id:
                raise ValueError(f"Line {line_no}, step {expected_no}: future INCOMPLETE steps require empty evidence_id")
            if evidence_id:
                record = known_evidence.get(evidence_id)
                if record is None:
                    raise ValueError(f"Line {line_no}, step {expected_no}: unknown evidence_id {evidence_id!r}")
                if record["time"] > audit_at:
                    raise ValueError(f"Line {line_no}, step {expected_no}: evidence {evidence_id!r} is after audit_at")
    return len(rows)


def main() -> None:
    try:
        count = validate()
    except (OSError, ValueError) as exc:
        raise SystemExit(f"INVALID: {exc}") from exc
    print(f"Valid output: {count} cases; schema, status, steps, phase order, and evidence-time checks passed")


if __name__ == "__main__":
    main()
