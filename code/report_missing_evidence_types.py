"""Report evidence source and cutoff details for unmatched sample tuples."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_index import build_index, read_manifest
from identity_resolution import load_index
from main import DATASET, read_rows
from step_generation import build_candidate
from timestamps import parse_timestamp


def main() -> None:
    requests = read_rows(DATASET / "sample_deletion_requests.csv")
    gold = {r["case_id"]: r for r in read_rows(DATASET / "sample_output.csv")}
    identities = load_index()
    predicted = {r["case_id"]: r for r in build_candidate(requests, build_index(), identities)}
    manifest = {r["file_id"]: r for r in read_manifest()}
    facts = build_index()
    counts: Counter[str] = Counter()
    for case in requests:
        case_id = case["case_id"]
        expected = json.loads(gold[case_id]["steps_json"])
        actual = json.loads(predicted[case_id]["steps_json"])
        key = lambda s: tuple(s.get(k) for k in ("phase", "operation", "system_id", "resource_id", "state"))
        got = {key(s) for s in actual}
        for step in expected:
            if key(step) in got:
                continue
            evidence_id = step.get("evidence_id", "")
            source = manifest.get(evidence_id)
            if source:
                file_type = Path(source["file_path"]).suffix.lstrip(".").upper()
                captured = source["captured_at"]
                cutoff_result = "before_or_at" if parse_timestamp(captured) <= parse_timestamp(case["audit_at"]) else "after"
                has_fact = any(f.get("file_id") == evidence_id
                               and step.get("resource_id") in f.get("resource_ids", []) for f in facts)
            else:
                file_type = "NO_EVIDENCE_ID" if not evidence_id else "NON_FILE_ID"
                captured = "—"
                cutoff_result = "—"
                has_fact = False
            counts[file_type] += 1
            print(f"{case_id}\t{key(step)}\t{evidence_id or '—'}\t{file_type}\t"
                  f"{captured} vs {case['audit_at']} ({cutoff_result})\tresource_fact={has_fact}")
    print("MISSING_TUPLES_BY_CITED_FILE_TYPE", dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
