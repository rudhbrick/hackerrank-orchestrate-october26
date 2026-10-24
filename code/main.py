"""Deterministic Tier 1 writer; deletion audits are explicitly placeholders."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
OUTPUT = ROOT / "output.csv"
FIELDS = ["case_id", "deletion_status", "steps_json"]

NON_DELETION_CUES = (
    "access my data", "access to my data", "send me my data", "export my data",
    "correct my", "update my", "change my", "rectify", "marketing",
    "unsubscribe", "opt out", "opt-out", "stop sending", "do not delete",
    "don't delete", "no deletion", "borrar publicidad", "désabonner",
)
DELETION_CUES = (
    "delete", "deletion", "erase", "erasure", "remove my personal",
    "remove my data", "remove my account", "close my account", "close this account",
    "forget me", "right to be forgotten", "suppression", "effacer", "supprimer",
    "löschen", "loeschen", "eliminar", "borrar mis datos", "elimina mis datos",
    "cancellare", "消除", "削除",
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def authorizes_deletion(text: str) -> bool:
    normalized = " ".join((text or "").casefold().split())
    if any(cue in normalized for cue in NON_DELETION_CUES):
        return False
    return any(cue in normalized for cue in DELETION_CUES)


def build_rows(requests: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for request in sorted(requests, key=lambda row: row["case_id"]):
        status = "INCOMPLETE" if authorizes_deletion(request.get("request_text", "")) else "NOT_APPLICABLE"
        result.append({
            "case_id": request["case_id"],
            "deletion_status": status,
            "steps_json": "[]",
        })
    return result


def write_rows(rows: list[dict[str, str]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    requests = read_rows(DATASET / "deletion_requests.csv")
    rows = build_rows(requests)
    write_rows(rows, OUTPUT)
    print(f"Wrote {len(rows)} rows to {OUTPUT}")
    print("WARNING: INCOMPLETE is a placeholder; no deletion evidence audit is implemented.")


if __name__ == "__main__":
    main()
