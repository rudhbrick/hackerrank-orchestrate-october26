"""Resolve current and historical subject identifiers from participant-facing CSVs."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def normalize(value: str) -> str:
    return " ".join((value or "").casefold().split())


class IdentityIndex:
    """Indexes identity values (including audit old/new values) to stable user IDs."""

    FIELDS = {"email", "name", "full_name", "phone", "email_hash"}

    def __init__(self, identities: list[dict[str, str]], audits: list[dict[str, str]]):
        self.values: dict[str, set[str]] = {}
        self.by_user: dict[str, dict[str, set[str]]] = {}
        for identity in identities:
            uid = identity["user_id"]
            self._add(uid, "user_id", uid)
            for field in self.FIELDS:
                value = identity.get(field, "")
                self._add(uid, field, value)
        for audit in audits:
            field = normalize(audit.get("field_name", ""))
            if field in self.FIELDS:
                self._add(audit["user_id"], field, audit.get("old_value", ""))
                self._add(audit["user_id"], field, audit.get("new_value", ""))

    def _add(self, uid: str, field: str, value: str) -> None:
        key = normalize(value)
        if not key:
            return
        self.values.setdefault(key, set()).add(uid)
        self.by_user.setdefault(uid, {}).setdefault(field, set()).add(key)

    def resolve(self, value: str) -> set[str]:
        return set(self.values.get(normalize(value), set()))

    def field_values(self, user_id: str, field: str) -> set[str]:
        return set(self.by_user.get(user_id, {}).get(field, set()))


def load_index() -> IdentityIndex:
    return IdentityIndex(rows(DATASET / "user_identities.csv"), rows(DATASET / "user_audit_log.csv"))
