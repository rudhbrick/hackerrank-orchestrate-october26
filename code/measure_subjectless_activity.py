"""Evaluate conservative links from subject-less deletion activity rows."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_index import build_index, text_identifiers
from identity_resolution import load_index, normalize, rows as read_csv
import main as main_module
from main import DATASET, _subject_values, read_rows
from step_generation import build_candidate
from timestamps import parse_timestamp

TUPLE_FIELDS = ("phase", "operation", "system_id", "resource_id", "state")
DELETE_EVENT = re.compile(r"delete|deletion|erase|remov|purge|redact|anonym", re.I)


def tuple_key(step: dict[str, str]) -> tuple[str, ...]:
    return tuple(step[field] for field in TUPLE_FIELDS)


def main() -> None:
    requests = read_rows(DATASET / "sample_deletion_requests.csv")
    gold = {row["case_id"]: row for row in read_rows(DATASET / "sample_output.csv")}
    identities = load_index()
    all_ids = set(identities.values)
    activities = read_csv(DATASET / "system_activity.csv")
    facts = build_index()
    generated = {row["case_id"]: row for row in build_candidate(requests, facts, identities)}

    missing_by_group: Counter[tuple[str, str, str]] = Counter()
    missing_absent: list[tuple[dict[str, str], dict[str, str]]] = []
    expected_pairs: set[tuple[str, str, str]] = set()
    base_discovered: set[tuple[str, str, str]] = set()
    for case in requests:
        case_id = case["case_id"]
        expected_steps = [json.loads(gold[case_id]["steps_json"])]
        generated_steps = json.loads(generated[case_id]["steps_json"])
        exp = {tuple_key(step): step for step in expected_steps[0]}
        got = {tuple_key(step): step for step in generated_steps}
        for key in exp.keys() - got.keys():
            phase, operation, system, resource, _state = key
            missing_by_group[(phase, operation, system)] += 1
            if operation == "VERIFY_RECORD_ABSENT":
                missing_absent.append((case, exp[key]))
        expected_pairs.update((case_id, step["system_id"], step["resource_id"]) for step in exp.values())
        base_discovered.update((case_id, str(f.get("system", "")), resource)
                               for f in main_module.latest_subject_resources(case, facts, identities)
                               for resource in f.get("resource_ids", [])
                               if f.get("system") and resource)

    print("Missing expected tuple counts by phase, operation, system_id:")
    for (phase, operation, system), count in sorted(missing_by_group.items()):
        print(f"  {phase},{operation},{system}: {count}")

    print("Missing VERIFY_RECORD_ABSENT resource appearances:")
    for case, step in sorted(missing_absent, key=lambda pair: (pair[0]["case_id"], pair[1]["resource_id"])):
        resource = step["resource_id"]
        uid_set = identities.resolve(case["email"])
        subject_values = _subject_values(case, identities)
        activity_hits = []
        for row in activities:
            if row.get("resource_id") != resource:
                continue
            identifiers = text_identifiers(" ".join(row.values()))
            values = {value.casefold() for values in identifiers.values() for value in values}
            linked = any(identities.resolve(value) & uid_set for value in values)
            any_subject = any(value in all_ids for value in values)
            activity_hits.append((row["activity_id"], row["target_system"], row["event_type"],
                                  row["event_time"], linked, any_subject))
        evidence_hits = []
        for fact in facts:
            if resource not in fact.get("resource_ids", []):
                continue
            values = {value.casefold() for vals in fact.get("identifiers", {}).values() for value in vals}
            linked = bool(subject_values & values)
            any_subject = any(value in all_ids for value in values)
            evidence_hits.append((fact.get("file_id", ""), fact.get("system", ""),
                                  fact.get("captured_at", ""), linked, any_subject))
        identity_rows = [
            (path.name, row)
            for path in (DATASET / "user_identities.csv", DATASET / "user_audit_log.csv")
            for row in read_csv(path)
            if resource in {value for value in row.values()}
        ]
        print(f"  {case['case_id']} {resource}: activity={activity_hits}; evidence={evidence_hits}; identity_rows={len(identity_rows)}")

    # Evaluate candidates separately for each time window. Only rows with no identity
    # identifier matching any participant are considered subject-less.
    subjectless = []
    for row in activities:
        identifiers = text_identifiers(" ".join(row.values()))
        values = {value.casefold() for vals in identifiers.values() for value in vals}
        normalized_row = normalize(" ".join(row.values()))
        if any(value in all_ids for value in values) or any(value in normalized_row for value in all_ids):
            continue
        if not DELETE_EVENT.search(row.get("event_type", "")):
            continue
        subjectless.append(row)
    print(f"Subject-less deletion-type activity rows: {len(subjectless)} / {len(activities)}")
    for label, end_field in (("requested_at..reported_at", "reported_at"),
                             ("requested_at..audit_at", "audit_at")):
        activity_pairs: set[tuple[str, str, str]] = set()
        for case in requests:
            start = parse_timestamp(case["requested_at"])
            end = parse_timestamp(case[end_field])
            for row in subjectless:
                when = parse_timestamp(row["event_time"])
                if (row["target_system"] and row["resource_id"]
                        and row["event_type"] and start <= when <= end):
                    activity_pairs.add((case["case_id"], row["target_system"], row["resource_id"]))
        combined = base_discovered | activity_pairs
        matched_activity = len(activity_pairs & expected_pairs)
        activity_precision = matched_activity / len(activity_pairs) if activity_pairs else 0.0
        activity_recall = matched_activity / len(expected_pairs) if expected_pairs else 0.0
        matched_combined = len(combined & expected_pairs)
        combined_precision = matched_combined / len(combined) if combined else 0.0
        combined_recall = matched_combined / len(expected_pairs) if expected_pairs else 0.0
        print(f"{label}: activity-only pairs={len(activity_pairs)}, matched={matched_activity}, "
              f"precision={activity_precision:.1%}, recall={activity_recall:.1%}; "
              f"combined precision={combined_precision:.1%}, recall={combined_recall:.1%}")


if __name__ == "__main__":
    main()
