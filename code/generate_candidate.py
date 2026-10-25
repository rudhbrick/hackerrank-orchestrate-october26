"""Generate the review candidate without modifying the submission output.csv."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_index import build_index
from identity_resolution import load_index
from main import DATASET, read_rows, write_rows
from step_generation import build_candidate


def main() -> None:
    requests = read_rows(DATASET / "deletion_requests.csv")
    facts = build_index()
    identities = load_index()
    rows = build_candidate(requests, facts, identities)
    target = ROOT / "output.candidate.csv"
    write_rows(rows, target)
    print(f"Wrote {len(rows)} rows to {target}")


if __name__ == "__main__":
    main()
