"""Evaluate the no-LLM request-intent classifier on the hand-labeled set."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from main import authorizes_deletion

ROOT = Path(__file__).resolve().parents[1]
EVAL_FILE = ROOT / "code" / "evaluation" / "intent_eval.csv"
LABELS = ("DELETE", "NOT_DELETION")


def main() -> None:
    with EVAL_FILE.open(encoding="utf-8-sig", newline="") as f:
        cases = list(csv.DictReader(f))

    confusion = Counter()
    errors: dict[str, list[dict[str, str]]] = defaultdict(list)
    correct = 0
    for case in cases:
        actual = case["expected_intent"]
        predicted = "DELETE" if authorizes_deletion(case["request_text"]) else "NOT_DELETION"
        if actual not in LABELS:
            raise SystemExit(f"Invalid expected_intent in {case['case_id']}: {actual}")
        confusion[(actual, predicted)] += 1
        if actual == predicted:
            correct += 1
        else:
            errors[case["cause"]].append({
                "case_id": case["case_id"],
                "expected": actual,
                "predicted": predicted,
                "text": case["request_text"],
            })

    print(f"Cases: {len(cases)}")
    print(f"Accuracy: {correct}/{len(cases)} = {correct / len(cases):.1%}")
    print("Confusion matrix (rows=actual, columns=predicted):")
    print("actual\\predicted," + ",".join(LABELS))
    for actual in LABELS:
        print(actual + "," + ",".join(str(confusion[(actual, predicted)]) for predicted in LABELS))
    print("Misclassified rows grouped by cause:")
    if not errors:
        print("  None")
    for cause in sorted(errors):
        print(f"  {cause} ({len(errors[cause])})")
        for error in errors[cause]:
            print(f"    {error['case_id']}: expected={error['expected']}, predicted={error['predicted']} | {error['text']}")


if __name__ == "__main__":
    main()
