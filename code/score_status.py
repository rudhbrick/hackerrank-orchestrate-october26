"""Evaluate only deterministic request intent and status verdicts on public fixtures."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from evidence_index import build_index
from identity_resolution import load_index
from main import DATASET, ROOT, audit_status, classify_intent, read_rows, _fact_values, _subject_values


def score(request_path: Path, answer_path: Path, facts, identities, title: str) -> tuple[int, int]:
    requests = read_rows(request_path)
    answers = {r["case_id"]: r for r in read_rows(answer_path)}
    confusion = Counter()
    correct = 0
    print(f"{title}: {len(requests)} rows")
    for case in requests:
        cid = case["case_id"]
        gold = answers[cid]["deletion_status"]
        pred = audit_status(case, facts, identities)
        confusion[(gold, pred)] += 1
        correct += gold == pred
    labels = ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE", "UNRESOLVED")
    print(f"Status accuracy: {correct}/{len(requests)} = {correct / len(requests):.1%}")
    print("Confusion matrix (rows=gold, columns=prediction):")
    print("gold\\pred," + ",".join(labels))
    for actual in labels:
        print(actual + "," + ",".join(str(confusion[(actual, pred)]) for pred in labels))
    for case in requests:
        cid = case["case_id"]
        gold = answers[cid]["deletion_status"]
        pred = audit_status(case, facts, identities)
        if gold != pred:
            values = _subject_values(case, identities)
            linked = [f for f in facts if f.get("resource_ids") and values & _fact_values(f)]
            reason = f"intent={classify_intent(case.get('request_text',''))}; linked_facts={len(linked)}"
            print(f"MISS {cid}: gold={gold}, predicted={pred}; {reason}")
    return correct, len(requests)


def main() -> None:
    facts = build_index()
    identities = load_index()
    score(DATASET / "sample_deletion_requests.csv", DATASET / "sample_output.csv", facts, identities, "Public samples")
    gate = ROOT / "code" / "evaluation" / "intent_eval.csv"
    cases = read_rows(gate)
    correct = unresolved = 0
    print(f"\nIntent gate: {len(cases)} rows")
    for case in cases:
        pred = classify_intent(case["request_text"])
        unresolved += pred == "UNRESOLVED"
        expected = "DELETE" if case["expected_intent"] == "DELETE" else "NOT_DELETION"
        correct += pred == expected
        if pred != expected:
            print(f"GATE MISS {case['case_id']}: expected={expected}, predicted={pred} ({case['cause']})")
    print(f"Intent accuracy: {correct}/{len(cases)} = {correct / len(cases):.1%}; unresolved={unresolved}")
    extras = ROOT / "evaluation" / "extra_cases"
    if (extras / "extra_requests.csv").exists() and (extras / "extra_expected.csv").exists():
        score(extras / "extra_requests.csv", extras / "extra_expected.csv", facts, identities, "Extra cases (separate)")


if __name__ == "__main__":
    main()
