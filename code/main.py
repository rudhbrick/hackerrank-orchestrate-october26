"""Small deterministic baseline for Ghost Data Still Exists.

This scaffold classifies request intent and emits contract-shaped rows. For
requests authorizing deletion, it conservatively reports INCOMPLETE but does
not yet build evidence-backed findings or remediation steps.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
OUTPUT = ROOT / "output.csv"

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


def read_rows(filename: str) -> list[dict[str, str]]:
    with (DATASET / filename).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def authorizes_deletion(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    if any(cue in normalized for cue in NON_DELETION_CUES):
        return False
    return any(cue in normalized for cue in DELETION_CUES)


def main() -> None:
    requests = read_rows("deletion_requests.csv")
    # Load the supporting inputs so a clean run also confirms they are present
    # and readable. Evidence interpretation is intentionally outside this stub.
    identities = read_rows("user_identities.csv")
    identity_history = read_rows("user_audit_log.csv")
    activities = read_rows("system_activity.csv")
    rules = read_rows("deletion_rules.csv")
    evidence_manifest = read_rows("evidence_files.csv")
    if not all((identities, identity_history, activities, rules, evidence_manifest)):
        raise ValueError("One or more supporting dataset files are empty")

    result = []
    for request in sorted(requests, key=lambda row: row["case_id"]):
        if authorizes_deletion(request["request_text"]):
            # Baseline placeholder: evidence-backed steps are not implemented.
            status = "INCOMPLETE"
            steps = []
        else:
            status = "NOT_APPLICABLE"
            steps = []
        result.append({
            "case_id": request["case_id"],
            "deletion_status": status,
            "steps_json": json.dumps(steps, ensure_ascii=False, separators=(",", ":")),
        })

    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(result)
    print(f"Wrote {len(result)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
