"""Deterministic, content-cached extraction of participant-facing evidence facts."""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from timestamps import parse_timestamp

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
CACHE = ROOT / ".cache" / "evidence_facts"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
HASH_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
ID_TOKEN = r"(?:user|account|support|search|export|analytics|audit_record|tombstone|data_flow|backup|order|invoice|ticket|record|customer|event|job|sync|restore|index|replica|ord)[_-](?:[0-9]+|[a-f0-9]{4,})"
ID_RE = re.compile(rf"\b{ID_TOKEN}\b", re.I)
RESOURCE_FIELD_RE = re.compile(rf"(?i)\b(?:resource_id|record_id|target_resource|resource)\s*[:=]\s*(?:\\)?\s*[\"']?({ID_TOKEN})\b")
RESOURCE_REFERENCE_RE = re.compile(rf"(?i)\breference\b[^\r\n]{{0,100}}?/\s*({ID_TOKEN})\b")
RESOURCE_NAMED_RE = re.compile(rf"(?i)\b(?:event\s+reference|resource(?:\s+id)?|record(?:\s+id)?|order(?:\s+id|\s+number)?|invoice(?:\s+id)?|ticket(?:\s+id)?|audit\s+record)\s*[:=#-]?\s*[\"']?({ID_TOKEN})\b")
LOG_ATTR_RE = re.compile(r"(?i)\b([a-z][a-z0-9_]*)\s*[:=]\s*(?:\\)?(?:\"([^\"]*)\"|'([^']*)'|([^,}\s]+))")
PHONE_RE = re.compile(r"(?<!\w)\+?[0-9][0-9 ()-]{6,}[0-9](?!\w)")
RESOURCE_KEYS = {"resource_id", "record_id"}
RESOURCE_REFERENCE_KEYS = {"source_resource_id", "parent_resource_id", "origin_resource_id", "related_resource_id"}
SYSTEM_KEYS = {"system", "system_id", "data_store", "source_system", "target_system", "service", "platform", "origin"}
NAME_KEYS = {"name", "full_name", "customer_name", "requester_name", "contact_name", "account_holder_name"}
STATE_KEYS = {"result", "status", "status_code", "account_status", "record_type", "data_category",
              "required_action", "enabled", "restore_allowed", "last_delivery_status", "deletion_state",
              "redacted", "anonymized", "is_deleted", "profile", "customer_reference", "subject_reference"}


def read_manifest() -> list[dict[str, str]]:
    with (DATASET / "evidence_files.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def policy_categories() -> set[str]:
    with (DATASET / "deletion_rules.csv").open(encoding="utf-8-sig", newline="") as stream:
        return {row["data_category"].casefold() for row in csv.DictReader(stream)}


def norm(value: Any) -> str:
    return " ".join(str(value).casefold().split()) if value is not None else ""


def text_identifiers(text: str) -> dict[str, list[str]]:
    emails = sorted({norm(x) for x in EMAIL_RE.findall(text)})
    hashes = sorted({x.lower() for x in HASH_RE.findall(text)})
    all_ids = sorted({norm(x) for x in ID_RE.findall(text)})
    user_ids = [x for x in all_ids if x.startswith("user_")]
    phones = sorted({re.sub(r"\s+", " ", x.strip()) for x in PHONE_RE.findall(text)})
    names = sorted({norm(x) for x in re.findall(r"(?i)\b(?:full_name|customer_name|name)\s*[:=]\s*[\"']([^\"';,]+)", text)})
    found: dict[str, list[str]] = {}
    if emails: found["email"] = emails
    if hashes: found["email_hash"] = hashes
    if user_ids: found["user_id"] = user_ids
    if phones: found["phone"] = phones
    if names: found["name"] = names
    return found


def system_value(obj: dict[str, Any], fallback: str) -> str:
    for key, value in obj.items():
        if key.casefold() in SYSTEM_KEYS and isinstance(value, (str, int)):
            return norm(value)
    return fallback


def resource_ids_in_text(text: str) -> set[str]:
    """Find identifiers explicitly labeled as resource/record/event references."""
    return ({norm(value) for value in RESOURCE_FIELD_RE.findall(text)}
            | {norm(value) for value in RESOURCE_REFERENCE_RE.findall(text)}
            | {norm(value) for value in RESOURCE_NAMED_RE.findall(text)})


def line_attributes(line: str) -> dict[str, Any]:
    """Extract compact typed fields from JSON-like and key=value log records."""
    keep = {"event", "record_type", "data_category", "category", "file", "result", "status",
            "status_code", "rows", "http_status", "enabled", "restore_allowed", "redacted", "anonymized",
            "last_delivery_status", "scheduler_registered", "last_run"}
    attrs = {}
    for key, quoted, single, bare in LOG_ATTR_RE.findall(line):
        key = key.casefold()
        if key in keep:
            value = (quoted or single or bare).rstrip("\\")
            if value.casefold() in {"true", "false"}:
                attrs[key] = value.casefold() == "true"
            elif value.isdigit():
                attrs[key] = int(value)
            else:
                attrs[key] = value
    return attrs


def resource_system(resource_id: str, fallback: str) -> str:
    prefix = resource_id.casefold().split("_")[0].split("-")[0]
    return {"account": "account_service", "search": "search_service", "analytics": "analytics_platform",
            "support": "support_platform", "export": "export_service", "audit": "security_service",
            "tombstone": "identity_service", "data": "integration_service", "backup": "backup_service"}.get(prefix, fallback)


def object_facts(obj: Any, file_id: str, captured_at: str, fallback: str, parent: str = "") -> list[dict[str, Any]]:
    result = []
    if isinstance(obj, dict):
        resources: list[tuple[str, str]] = []
        identifiers: dict[str, set[str]] = {}
        attributes: dict[str, Any] = {}
        has_record_key = any(key.casefold() in RESOURCE_KEYS or
                             (key.casefold().endswith("_resource_id") and key.casefold() not in RESOURCE_REFERENCE_KEYS)
                             for key in obj)
        for key, value in obj.items():
            k = key.casefold()
            if k in STATE_KEYS:
                attributes[k] = value
            is_primary_resource = k in RESOURCE_KEYS or (k.endswith("_resource_id") and k not in RESOURCE_REFERENCE_KEYS)
            # account_id is commonly a foreign key on search/support rows. Treat it
            # as a resource only when it is the row's sole key in an account table.
            is_account_record = (k == "account_id" and not has_record_key
                                 and any(token in parent.casefold() for token in ("account", "profile")))
            if isinstance(value, (str, int, float)) and (is_primary_resource or is_account_record) and str(value):
                resources.append((norm(value), k))
            if isinstance(value, str) and value.strip():
                field = None
                if "email" in k or "mail" in k:
                    field = "email_hash" if "hash" in k else "email"
                elif "phone" in k or "mobile" in k or "telephone" in k:
                    field = "phone"
                elif "hash" in k:
                    field = "email_hash"
                elif k in NAME_KEYS:
                    field = "name"
                elif k in {"user_id", "subject_reference", "customer_reference", "subject_id", "user_reference", "customer_id", "subject_selector"} and value.casefold().startswith("user_"):
                    field = "user_id"
                elif k in {"subject_reference", "customer_reference", "user_reference", "lookup_value", "subject_key"} and EMAIL_RE.fullmatch(value.strip()):
                    field = "email"
                elif k in {"lookup_value", "correlation_key", "subject_key"}:
                    if EMAIL_RE.fullmatch(value.strip()): field = "email"
                    elif HASH_RE.fullmatch(value.strip()): field = "email_hash"
                    elif value.casefold().startswith("user_"): field = "user_id"
                if field:
                    identifiers.setdefault(field, set()).add(norm(value))
        if resources:
            system = system_value(obj, fallback)
            for resource, key in resources:
                resource_sys = resource_system(resource, system)
                result.append({"file_id": file_id, "captured_at": captured_at,
                               "system": resource_sys, "resource_ids": [resource],
                               "identifiers": {k: sorted(v) for k, v in identifiers.items()},
                               "attributes": attributes})
        elif identifiers:
            result.append({"file_id": file_id, "captured_at": captured_at, "system": system_value(obj, fallback),
                           "resource_ids": [], "identifiers": {k: sorted(v) for k, v in identifiers.items()},
                           "attributes": attributes})
        child_facts = []
        for key, value in obj.items():
            child_facts.extend(object_facts(value, file_id, captured_at, fallback, key))
        if resources and result:
            # Nested payloads (for example a SQL row's record_json/document) are
            # part of the enclosing resource. Carry their identifiers back to that
            # resource, but never across a different explicit resource ID.
            for fact in result:
                resource = (fact.get("resource_ids") or [""])[0]
                related = [child for child in child_facts
                           if not child.get("resource_ids")
                           or child.get("resource_ids") == [resource]]
                merged_ids = {k: set(v) for k, v in fact.get("identifiers", {}).items()}
                merged_attrs = dict(fact.get("attributes", {}))
                for child in related:
                    for field, values in child.get("identifiers", {}).items():
                        merged_ids.setdefault(field, set()).update(values)
                    merged_attrs.update(child.get("attributes", {}))
                fact["identifiers"] = {k: sorted(v) for k, v in merged_ids.items()}
                fact["attributes"] = merged_attrs
        result.extend(child_facts)
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
                for column, value in list(record.items()):
                    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
                        try:
                            record[column] = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                table_facts = object_facts(record, file_id, captured_at, fallback)
                for fact in table_facts:
                    # Table/source identity keeps primary, regional and replica observations separate.
                    fact["source"] = table
                facts.extend(table_facts)
        return facts
    finally:
        db.close()


def _text_facts(text: str, file_id: str, captured_at: str, fallback: str) -> list[dict[str, Any]]:
    identifiers = text_identifiers(text)
    resources = sorted(resource_ids_in_text(text))
    service = re.search(r"(?i)\bservice\s*=\s*[\"']?([A-Za-z0-9_-]+)", text)
    default_system = norm(service.group(1)) if service else fallback
    if resources:
        return [{"file_id": file_id, "captured_at": captured_at,
                 "system": resource_system(resource, default_system), "resource_ids": [resource],
                 "identifiers": identifiers} for resource in resources]
    if identifiers:
        return [{"file_id": file_id, "captured_at": captured_at, "system": default_system,
                 "resource_ids": [], "identifiers": identifiers}]
    return []


def _pdf_resource_facts(text: str, file_id: str, captured_at: str, fallback: str) -> list[dict[str, Any]]:
    """PDF text often names row IDs without a resource_id label; retain row scope."""
    identifiers = text_identifiers(text)
    resource_prefixes = ("account_", "support_", "search_", "export_", "analytics_",
                        "audit_record_", "tombstone_", "data_flow_", "backup_",
                        "sync_", "job_", "restore_", "index_", "replica_", "record_")
    resources = sorted({norm(value) for value in ID_RE.findall(text)
                        if norm(value).startswith(resource_prefixes)})
    if resources:
        return [{"file_id": file_id, "captured_at": captured_at,
                 "system": resource_system(resource, fallback), "resource_ids": [resource],
                 "identifiers": identifiers} for resource in resources]
    return _text_facts(text, file_id, captured_at, fallback)


def _pipe_record_facts(line: str, file_id: str, captured_at: str, fallback: str) -> list[dict[str, Any]]:
    cells = [cell.strip() for cell in line.split("|")]
    facts = []
    categories = policy_categories()
    state_values = {"active", "disabled", "not_found", "absent", "deleted", "found", "present",
                    "identifiable", "anonymized", "redacted", "retained", "blocked"}
    for index, cell in enumerate(cells):
        if index == 0 or not re.fullmatch(ID_TOKEN, cell, re.I):
            continue
        resource_id = cell
        system = norm(cells[index - 1]) or fallback
        identifiers = text_identifiers(" ".join(cells[index + 1:]))
        attributes: dict[str, Any] = {}
        for following_cell in cells[index + 1:index + 3]:
            value = norm(following_cell)
            if value in state_values:
                attributes["result"] = value
            elif value in categories and "record_type" not in attributes:
                attributes["record_type"] = norm(following_cell).replace(" ", "_")
        facts.append({"file_id": file_id, "captured_at": captured_at,
                      "system": resource_system(resource_id, system), "resource_ids": [norm(resource_id)],
                      "identifiers": identifiers, "attributes": attributes})
    return facts


def _log_facts(text: str, file_id: str, captured_at: str, fallback: str) -> list[dict[str, Any]]:
    # Join related log events only within their explicit trace_id; never join a whole log file.
    traces: dict[str, dict[str, Any]] = {}
    standalone: list[dict[str, Any]] = []
    for line in text.splitlines():
        trace_match = re.search(r"(?i)\btrace_id\s*=\s*[\"']?([A-Za-z0-9_-]+)", line)
        ids = text_identifiers(line)
        resources = sorted(resource_ids_in_text(line))
        service = re.search(r"(?i)\b(?:service|function)\s*[:=]\s*(?:\\)?[\"']?([A-Za-z0-9_-]+)", line)
        default_system = norm(service.group(1)) if service else fallback
        if trace_match:
            trace = traces.setdefault(trace_match.group(1), {"identifiers": {}, "resources": {}, "attributes": {}})
            for field, values in ids.items():
                trace["identifiers"].setdefault(field, set()).update(values)
            for resource in resources:
                trace["resources"][resource] = resource_system(resource, default_system)
            trace["attributes"].update(line_attributes(line))
            outcome = re.search(r"(?i)\b(rows|http_status|status_code)\s*=\s*(\d+)\b", line)
            if outcome:
                trace.setdefault("outcomes", set()).add(f"{outcome.group(1).casefold()}={outcome.group(2)}")
        elif ids or resources:
            if resources:
                outcome = re.search(r"(?i)\b(rows|http_status|status_code)\s*=\s*(\d+)\b", line)
                standalone.extend({"file_id": file_id, "captured_at": captured_at,
                                   "system": resource_system(resource, default_system),
                                   "resource_ids": [resource], "identifiers": ids,
                                   "attributes": line_attributes(line),
                                   "outcomes": [f"{outcome.group(1).casefold()}={outcome.group(2)}"] if outcome else []}
                                  for resource in resources)
            else:
                standalone.append({"file_id": file_id, "captured_at": captured_at, "system": default_system,
                                   "resource_ids": [], "identifiers": ids})
    for trace in traces.values():
        for resource, system in trace["resources"].items():
            standalone.append({"file_id": file_id, "captured_at": captured_at, "system": system,
                               "resource_ids": [resource],
                               "identifiers": {k: sorted(v) for k, v in trace["identifiers"].items()},
                               "attributes": trace["attributes"],
                               "outcomes": sorted(trace.get("outcomes", set()))})
    return standalone


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
        facts = []
        for page in PdfReader(str(path)).pages:
            text = page.extract_text() or ""
            # Scope identifiers to PDF record blocks instead of joining an entire page.
            blocks = re.split(r"(?im)(?=^\s*(?:Record|\d+)\s*$)", text)
            blocks = [block for block in blocks if block.strip()] or [text]
            facts.extend(fact for block in blocks
                         for fact in _pdf_resource_facts(block, file_id, captured_at, fallback))
        return facts
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if suffix == ".log":
        return _log_facts(text, file_id, captured_at, fallback)
    # Pipe-delimited business records are scoped to rows; other plain text uses paragraph scope.
    pipe_facts = [fact for line in text.splitlines() for fact in _pipe_record_facts(line, file_id, captured_at, fallback)]
    if pipe_facts:
        return pipe_facts
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [fact for paragraph in paragraphs for fact in _text_facts(paragraph, file_id, captured_at, fallback)]


def _parse_overlay(path: Path) -> list[dict[str, Any]]:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ValueError("overlay must be inside the repository")
    with resolved.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = []
    for row in rows:
        identifiers = text_identifiers(" ".join(row.values()))
        resource_ids = [norm(row.get("resource_id", ""))] if row.get("resource_id") else []
        explicit_user = row.get("user_id", "")
        if explicit_user:
            identifiers.setdefault("user_id", []).append(norm(explicit_user))
        for field in ("email", "phone", "email_hash", "name"):
            value = row.get(field, "")
            if value:
                identifiers.setdefault(field, []).append(norm(value))
        result.append({"file_id": row.get("activity_id", ""),
                       "captured_at": row.get("event_time", ""),
                       "system": norm(row.get("target_system", "")),
                       "resource_ids": sorted(set(resource_ids)),
                       "identifiers": {key: sorted(set(vals)) for key, vals in identifiers.items()},
                       "overlay": True,
                       "activity_id": row.get("activity_id", "")})
    return result


def build_index(overlay_path: Path | None = None) -> list[dict[str, Any]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    facts: list[dict[str, Any]] = []
    for entry in read_manifest():
        path = DATASET / entry["file_path"]
        digest = hashlib.sha256(b"evidence-facts-v21\0" + path.read_bytes()).hexdigest()
        cache_path = CACHE / f"{digest}.json"
        if cache_path.exists():
            parsed = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            parsed = parse_file(path, entry["file_id"], entry["captured_at"])
            parsed = [{k: v for k, v in fact.items() if k not in {"file_id", "captured_at"}} for fact in parsed]
            cache_path.write_text(json.dumps(parsed, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        if not parsed:
            parsed = [{"system": path.stem.casefold(), "resource_ids": [], "identifiers": {},
                       "no_identifier_facts": True}]
        parsed = [{**fact, "file_id": entry["file_id"], "captured_at": entry["captured_at"],
                   "file_path": entry["file_path"]} for fact in parsed]
        facts.extend(parsed)
    if overlay_path is not None:
        facts.extend(_parse_overlay(overlay_path))
    return facts


def at_cutoff(facts: list[dict[str, Any]], audit_at: str) -> list[dict[str, Any]]:
    cutoff = parse_timestamp(audit_at)
    return [fact for fact in facts if parse_timestamp(fact["captured_at"]) <= cutoff]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the deterministic evidence index")
    parser.add_argument("--overlay", type=Path, help="Explicit repo-local activity overlay CSV to include")
    args = parser.parse_args()
    result = build_index(args.overlay)
    print(f"Indexed {len(result)} facts from {len(read_manifest())} evidence files; images flagged unparsed.")
    print("Overlay facts:", sum(bool(f.get("overlay")) for f in result))
