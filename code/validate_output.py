"""Structural checks for the root output.csv baseline."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEADER = ["case_id", "deletion_status", "steps_json"]
ALLOWED_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
EXPECTED_ROWS = 518


def main() -> None:
    output_path = ROOT / "output.csv"
    with output_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != EXPECTED_HEADER:
            raise SystemExit(f"Wrong column order: {reader.fieldnames!r}")
        rows = list(reader)

    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"Expected {EXPECTED_ROWS} data rows; found {len(rows)}")

    case_ids = [row["case_id"] for row in rows]
    if case_ids != sorted(case_ids) or len(set(case_ids)) != EXPECTED_ROWS:
        raise SystemExit("case_id values must be unique and sorted")

    for line_no, row in enumerate(rows, start=2):
        if row["deletion_status"] not in ALLOWED_STATUSES:
            raise SystemExit(f"Line {line_no}: invalid deletion_status {row['deletion_status']!r}")
        try:
            steps = json.loads(row["steps_json"])
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Line {line_no}: steps_json is not valid JSON: {exc}") from exc
        if not isinstance(steps, list):
            raise SystemExit(f"Line {line_no}: steps_json must be a JSON array")
        if row["deletion_status"] == "NOT_APPLICABLE" and steps:
            raise SystemExit(f"Line {line_no}: NOT_APPLICABLE requires an empty steps array")
        for number, step in enumerate(steps, start=1):
            if not isinstance(step, dict) or step.get("step_no") != number:
                raise SystemExit(f"Line {line_no}: step numbers must be consecutive from 1")

    print(f"Valid structure: {len(rows)} rows, expected columns, allowed statuses, valid JSON arrays")


if __name__ == "__main__":
    main()
