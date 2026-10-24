"""Score the deterministic writer against the public 32-case sample answers."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from main import DATASET, build_rows, read_rows

ROOT = Path(__file__).resolve().parents[1]
STEP_FIELDS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def main() -> None:
    requests = read_rows(DATASET / "sample_deletion_requests.csv")
    gold_rows = read_rows(DATASET / "sample_output.csv")
    predicted = build_rows(requests)
    gold_by_id = {row["case_id"]: row for row in gold_rows}
    pred_by_id = {row["case_id"]: row for row in predicted}
    if set(gold_by_id) != set(pred_by_id) or len(gold_by_id) != len(gold_rows):
        raise SystemExit("Sample input and answer case IDs do not match uniquely")

    statuses = Counter()
    status_correct = 0
    sequence_correct = 0
    step_correct = step_total = 0
    field_correct = field_total = 0
    gold_step_total = 0
    for case_id in sorted(gold_by_id):
        gold = gold_by_id[case_id]
        pred = pred_by_id[case_id]
        gs = json.loads(gold["steps_json"])
        ps = json.loads(pred["steps_json"])
        statuses[(gold["deletion_status"], pred["deletion_status"])] += 1
        status_correct += gold["deletion_status"] == pred["deletion_status"]
        sequence_correct += gs == ps
        gold_step_total += len(gs)
        step_total += max(len(gs), len(ps))
        for i in range(max(len(gs), len(ps))):
            gstep = gs[i] if i < len(gs) else {}
            pstep = ps[i] if i < len(ps) else {}
            step_correct += bool(gstep) and gstep == pstep
            for field in STEP_FIELDS:
                field_total += 1
                field_correct += field in gstep and field in pstep and gstep[field] == pstep[field]

    n = len(gold_rows)
    print(f"Cases: {n}")
    print(f"Status accuracy: {status_correct}/{n} = {status_correct / n:.1%}")
    print(f"Step accuracy (exact aligned steps): {step_correct}/{step_total} = {step_correct / step_total:.1%}" if step_total else "Step accuracy: n/a (no steps)")
    print(f"Field accuracy (7 fields per aligned step; missing steps count wrong): {field_correct}/{field_total} = {field_correct / field_total:.1%}" if field_total else "Field accuracy: n/a (no steps)")
    print(f"Sequence accuracy: {sequence_correct}/{n} = {sequence_correct / n:.1%}")
    print(f"Gold steps: {gold_step_total}")
    labels = ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE")
    print("Status confusion matrix (rows=gold, columns=predicted):")
    print("gold\\predicted," + ",".join(labels))
    for actual in labels:
        print(actual + "," + ",".join(str(statuses[(actual, pred)]) for pred in labels))


if __name__ == "__main__":
    main()
