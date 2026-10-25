"""Deterministic, content-cached extraction of participant-facing evidence facts."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
CACHE = ROOT / ".cache" / "evidence_facts"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
HASH_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
ID_RE = re.compile(r"\b(?:user|account|support|search|export|analytics|audit_record|tombstone|data_flow|backup|order|invoice|ticket|record|customer|event|job|sync|restore|index|replica)[_-](?:[0-9]+|[a-f0-9]{4,})\b", re.I)
PHONE_RE = re.compile(r"(?<!\w)\+?[0-9][0-9 ()-]{6,}[0-9](?!\w)")
RESOURCE_KEYS = {"resource_id", "record_id", "account_id"}
IDENTIFIER_KEYS = {"email", "email_address", "phone", "phone_number", "email_hash", "name", "full_name", "customer_name", "user_id", "subject_reference"}
SYSTEM_KEYS = {"system", "system_id", "data_store", "source_system", "target_system", "service", "platform", "origin"}


def read_manifest() -> list[dict[str, str]]:
    with (DATASET / "evidence_files.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def norm(value: Any) -> str:
    return " ".join(str(value).casefold().split()) if value is not None else ""


def text_identifiers(text: str) -> dict[str, list[str]]:
    emails = sorted({norm(x) for x in EMAIL_RE.findall(text)})
    hashes = sorted({x.lower() for x in HASH_RE.findall(text)})
    all_ids = sorted({norm(x) for x in ID_RE.findall(text)})
    ids = [x for x in all_ids if not x.startswith("user_")]
    user_ids = [x for x in all_ids if x.startswith("user_")]
    phones = sorted({re.sub(r"\s+", " ", x.strip()) for x in PHONE_RE.findall(text)})
    found: dict[str, list[str]] = {}
    if emails: found["email"] = emails
    if hashes: found["email_hash"] = hashes
    if ids: found["resource_or_user_id"] = ids
    if user_ids: found["user_id"] = user_ids
    if phones: found["phone"] = phones
    return found


def system_value(obj: dict[str, Any], fallback: str) -> str:
    for key, value in obj.items():
        if key.casefold() in SYSTEM_KEYS and isinstance(value, (str, int)):
            return norm(value)
    return fallback


def resource_system(resource_id: str, fallback: str) -> str:
    prefix = resource_id.casefold().split("_")[0].split("-")[0]
    return {"account": "account_service", "search": "search_service", "analytics": "analytics_platform",
            "support": "support_platform", "export": "export_service", "audit": "security_service",
            "tombstone": "identity_service", "data": "integration_service", "backup": "backup_service"}.get(prefix, fallback)


def object_facts(obj: Any, file_id: str, captured_at: str, fallback: str, parent: str = "") -> list[dict[str, Any]]:
    result = []
    if isinstance(obj, dict):
        resources: set[str] = set()
        identifiers: dict[str, set[str]] = {}
        for key, value in obj.items():
            k = key.casefold()
            if isinstance(value, (str, int, float)) and k in RESOURCE_KEYS and str(value):
                resources.add(norm(value))
            if isinstance(value, str) and k in IDENTIFIER_KEYS and value.strip():
                field = "email_hash" if "hash" in k else "email" if "email" in k else "phone" if "phone" in k else "user_id" if k in {"user_id", "subject_reference"} else "name"
                identifiers.setdefault(field, set()).add(norm(value))
        if resources or identifiers:
            system = system_value(obj, fallback)
            primary_resource = next((r for r in sorted(resources) if not r.startswith("user_")), next(iter(sorted(resources)), ""))
            result.append({"file_id": file_id, "captured_at": captured_at,
                           "system": resource_system(primary_resource, system) if primary_resource else system,
                           "resource_ids": sorted(resources),
                           "identifiers": {k: sorted(v) for k, v in identifiers.items()}})
        for key, value in obj.items():
            result.extend(object_facts(value, file_id, captured_at, fallback, key))
    elif isinstance(obj, list):
        for value in obj:
            result.extend(object_facts(value, file_id, captured_at, fallback, parent))
    return result


def parse_sql(path: Path, file_id: str, captured_at: str, fallback: str) -> list[dict[str, Any]]:
    # SQLite in-memory only: evidence is SQL text and never opens a persistent database.
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(path.read_text(encoding="utf-8", errors="replace"))
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        facts = []
        for table in tables:
            columns = [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]
            for row in db.execute(f'SELECT * FROM "{table}"'):
                record = dict(zip(columns, row))
                facts.extend(object_facts(record, file_id, captured_at, fallback))
        return facts
    finally:
        db.close()


def parse_file(path: Path, file_id: str, captured_at: str) -> list[dict[str, Any]]:
    fallback = path.stem.casefold()
    suffix = path.suffix.casefold()
    if suffix in IMAGE_SUFFIXES:
        return [{"file_id": file_id, "captured_at": captured_at, "system": fallback,
                 "resource_ids": [], "identifiers": {}, "unparsed_image": True}]
    if suffix == ".sql":
        return parse_sql(path, file_id, captured_at, fallback)
    if suffix == ".json":
        return object_facts(json.loads(path.read_text(encoding="utf-8-sig")), file_id, captured_at, fallback)
    if suffix == ".pdf":
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    else:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    # Log/TXT/PDF text: one normalized fact per matching line, retaining regex-grounded identifiers.
    facts = []
    for line in text.splitlines():
        ids = text_identifiers(line)
        resources = ids.pop("resource_or_user_id", [])
        if ids or resources:
            resource = resources[0] if resources else ""
            facts.append({"file_id": file_id, "captured_at": captured_at, "system": resource_system(resource, fallback),
                          "resource_ids": resources, "identifiers": ids})
    return facts


def build_index() -> list[dict[str, Any]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    facts: list[dict[str, Any]] = []
    for entry in read_manifest():
        path = DATASET / entry["file_path"]
        digest = hashlib.sha256(b"evidence-facts-v3\0" + path.read_bytes()).hexdigest()
        cache_path = CACHE / f"{digest}.json"
        if cache_path.exists():
            parsed = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            parsed = parse_file(path, entry["file_id"], entry["captured_at"])
            parsed = [{k: v for k, v in fact.items() if k not in {"file_id", "captured_at"}} for fact in parsed]
            cache_path.write_text(json.dumps(parsed, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        parsed = [{**fact, "file_id": entry["file_id"], "captured_at": entry["captured_at"]} for fact in parsed]
        facts.extend(parsed)
    return facts


def at_cutoff(facts: list[dict[str, Any]], audit_at: str) -> list[dict[str, Any]]:
    return [fact for fact in facts if fact["captured_at"] <= audit_at]


if __name__ == "__main__":
    result = build_index()
    print(f"Indexed {len(result)} facts from {len(read_manifest())} evidence files; images flagged unparsed.")
