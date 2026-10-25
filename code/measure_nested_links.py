"""Measure identifier propagation from nested evidence payloads."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main
from evidence_index import CACHE, DATASET, build_index, read_manifest
from identity_resolution import load_index


def old_v20_facts() -> list[dict]:
    result = []
    for item in read_manifest():
        path = DATASET / item["file_path"]
        digest = hashlib.sha256(b"evidence-facts-v20\0" + path.read_bytes()).hexdigest()
        cached = CACHE / f"{digest}.json"
        if not cached.exists():
            raise RuntimeError(f"Missing pre-propagation cache for {item['file_id']}")
        result.extend({**fact, "file_id": item["file_id"], "captured_at": item["captured_at"],
                       "file_path": item["file_path"]}
                      for fact in json.loads(cached.read_text(encoding="utf-8")))
    return result


def main_fn() -> None:
    from main import DATASET as dataset, read_rows
    requests = read_rows(dataset / "sample_deletion_requests.csv")
    gold = {r["case_id"]: r for r in read_rows(dataset / "sample_output.csv")}
    identities = load_index()
    old, new = old_v20_facts(), build_index()
    expected = {(case_id, step["system_id"], step["resource_id"])
                for case_id, row in gold.items() for step in json.loads(row["steps_json"])}
    offers: dict[str, set[tuple[str, str, str]]] = {"evidence_92": set(), "evidence_05": set()}
    for case in requests:
        case_id = case["case_id"]
        before = {(f["system"], rid) for f in main.latest_subject_resources(case, old, identities)
                  for rid in f.get("resource_ids", [])}
        after = {(f["system"], rid) for f in main.latest_subject_resources(case, new, identities)
                 for rid in f.get("resource_ids", [])}
        for system, resource in after - before:
            for file_id in offers:
                if any(f.get("file_id") == file_id and f.get("system") == system
                       and resource in f.get("resource_ids", [])
                       for f in main.latest_subject_resources(case, new, identities)):
                    offers[file_id].add((case_id, system, resource))
    for file_id, links in offers.items():
        matched = len(links & expected)
        print(f"{file_id}: new case/system/resource links={len(links)}, expected matches={matched}, "
              f"precision={matched/len(links):.1%}" if links else f"{file_id}: no new links")
        for link in sorted(links):
            print(" ", link, "expected" if link in expected else "extra")


if __name__ == "__main__":
    main_fn()
