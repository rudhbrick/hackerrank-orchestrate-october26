"""Deterministic intent and status verdicts; this module deliberately emits no steps."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from evidence_index import at_cutoff, build_index, read_manifest
from identity_resolution import load_index
from timestamps import parse_timestamp

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
OUTPUT = ROOT / "output.csv"
FIELDS = ["case_id", "deletion_status", "steps_json"]

DELETE_RE = re.compile(
    r"\b(?:delet\w*|eras\w*|remov\w*|clos\w*|destroy\w*|forget\w*|suppress\w*|"
    r"effac\w*|supprim\w*|elimin\w*|exclus\w*|borr\w*|apag\w*|retir\w*|"
    r"losch\w*|l?schen\w*|entfern\w*|cancell\w*)\b", re.I)
NONDELETE_RE = re.compile(
    r"\b(access|acces\w*|copy|copia|copie|send me|export|download|correct\w*|correction|"
    r"update|rectify|rectif\w*|corrig\w*|marketing|unsubscribe|opt[ -]?out|stop sending|"
    r"change|replace|keep|informacion|informacion|informacao|informacao|solicitud de informacion)\b", re.I)
NEGATED_DELETE_RE = re.compile(
    r"\b(?:do not|don't|dont|cannot|can't|can not|will not|won't|would not|wouldn't|never|without|"
    r"no|not|sin|sans|sem|nao|ne)\s+(?:(?:want|wish|need|intend|ask|solicit|quier|quer|demander|request)\w*\s+"
    r"(?:to|for|a|de)?\s*)?(?:a\s+)?(?:delet\w*|eras\w*|remov\w*|clos\w*|destroy\w*|forget\w*|"
    r"suppress\w*|effac\w*|supprim\w*|elimin\w*|exclus\w*|borr\w*|apag\w*|retir\w*|"
    r"losch\w*|l?schen\w*|entfern\w*|cancell\w*)\b|"
    r"\bnot\s+(?:a\s+)?(?:request|asking|requesting|seeking)\s+(?:to|for)\s+"
    r"(?:delet\w*|eras\w*|remov\w*|clos\w*|destroy\w*|forget\w*|suppress\w*)\b|"
    r"\bno\s+(?:es\s+una\s+)?(?:solicitud|pedido|demande|request)\s+(?:de|to|for)\s+"
    r"(?:delet\w*|eras\w*|remov\w*|supprim\w*|elimin\w*|borr\w*)\b",
    re.I,
)

# Intent vocabulary covers English, Portuguese, Spanish, French, Japanese and Korean,
# the languages present in this request corpus. East Asian expressions are Unicode-escaped
# so this source remains safe across Windows console encodings.
_EAST_ASIAN_INTENT = {
    "Japanese": {
        "delete": re.compile(r"\u524a\u9664|\u6d88\u53bb|\u6d88\u3057|\u6d88\u3057\u3066|\u6d88\u3059"),
        "negative": re.compile(r"\u524a\u9664\u3057\u306a\u3044|\u524a\u9664\u3092\u6c42\u3081\u306a\u3044|\u524a\u9664\u3092\u4f9d\u983c\u3057\u306a\u3044|\u524a\u9664\u3092\u4f9d\u983c\u3057\u3066\u3044\u307e\u305b\u3093|\u524a\u9664\u3092\u4f9d\u983c\u3057\u307e\u305b\u3093|\u6d88\u3055\u306a\u3044|\u524a\u9664\u3067\u306f\u306a\u304f|\u524a\u9664\u306e\u4f9d\u983c\u3067\u306f\u306a\u3044"),
        "request": re.compile(r"\u4f9d\u983c|\u304a\u9858\u3044\u3057\u307e\u3059|\u5e0c\u671b|\u304f\u3060\u3055\u3044|\u6c42\u3081"),
        "other": re.compile(r"\u958b\u793a|\u30a2\u30af\u30bb\u30b9|\u8a02\u6b63|\u4fee\u6b63|\u30b3\u30d4\u30fc|\u8907\u88fd|\u30a8\u30af\u30b9\u30dd\u30fc\u30c8|\u30de\u30fc\u30b1\u30c6\u30a3\u30f3\u30b0|\u914d\u4fe1\u505c\u6b62"),
    },
    "Korean": {
        "delete": re.compile(r"\uc0ad\uc81c|\uc81c\uac70|\uc9c0\uc6b0|\ud30c\uae30"),
        "negative": re.compile(r"\uc0ad\uc81c\ud558\uc9c0|\uc0ad\uc81c\s*\uc548|\uc0ad\uc81c\ub97c\s*\uc6d0\ud558\uc9c0|\uc0ad\uc81c\ub97c\s*\uc694\uccad\ud558\uc9c0|\uc9c0\uc6b0\uc9c0|\uc0ad\uc81c\uac00\s*\uc544\ub2c8\ub77c|\uc0ad\uc81c\s*\uc694\uccad\uc774\s*\uc544\ub2d9\ub2c8\ub2e4"),
        "request": re.compile(r"\uc694\uccad|\ubd80\ud0c1|\ud574\uc8fc\uc138\uc694|\ud574\s*\uc8fc\uc138\uc694|\ubc14\ub78d\ub2c8\ub2e4"),
        "other": re.compile(r"\uc5f4\ub78c|\uc811\uadfc|\uc815\uc815|\uc218\uc815|\ubcf5\uc0ac|\ub0b4\ubcf4\ub0b4\uae30|\ub9c8\ucf00\ud305|\uc218\uc2e0\s*\uac70\ubd80"),
    },
}

def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


_RULES = {row["data_category"].casefold(): row["required_action"].upper()
          for row in read_rows(DATASET / "deletion_rules.csv")}


def _ascii(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    # Dataset records include a few replacement-character mojibake strings.
    return value.casefold().replace("�", "e")


def classify_intent(text: str) -> str:
    """Classify deletion intent with stemmed negation and corpus-language vocabulary."""
    raw = text or ""
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", raw):
        rules = _EAST_ASIAN_INTENT["Japanese"]
        if rules["negative"].search(raw):
            return "NOT_DELETION"
        if rules["delete"].search(raw) and rules["request"].search(raw):
            return "DELETE"
        return "NOT_DELETION" if rules["other"].search(raw) else "UNRESOLVED"
    if re.search(r"[\uac00-\ud7af]", raw):
        rules = _EAST_ASIAN_INTENT["Korean"]
        if rules["negative"].search(raw):
            return "NOT_DELETION"
        if rules["delete"].search(raw) and rules["request"].search(raw):
            return "DELETE"
        return "NOT_DELETION" if rules["other"].search(raw) else "UNRESOLVED"

    normalized = " ".join(_ascii(raw).split())
    if not normalized:
        return "UNRESOLVED"
    if re.search(r"\b(right to be forgotten|right to erasure|derecho al olvido|direito ao esquecimento|droit a l'effacement)\b", normalized):
        return "DELETE"
    if re.search(r"\b(explain|how (?:can|do|to)|instructions? for)\b.{0,70}\b(delete|erase|remove|close)\b", normalized):
        return "NOT_DELETION"

    clauses = [x.strip() for x in re.split(
        r"[.!?;\n]+|\b(?:but|however|instead|rather|aunque|pero|mais|cependant|sondern)\b",
        normalized) if x.strip()]
    action_re = re.compile(
        r"\b(?:delet\w*|eras\w*|remov\w*|clos\w*|destroy\w*|forget\w*|suppress\w*|"
        r"suppression\w*|effac\w*|supprim\w*|elimin\w*|exclus\w*|borr\w*|apag\w*|"
        r"retir\w*|losch\w*|l?schen\w*|entfern\w*|cancell\w*)\b", re.I)
    negated_action = re.compile(
        r"\b(?:do not|don't|dont|cannot|can't|can not|will not|won't|would not|wouldn't|never|"
        r"without|no|not|sin|sans|sem|nao|ne)\s+(?:(?:want|wish|need|intend|ask|solicit|quier|"
        r"demander|request)\w*\s+(?:to|for|a|de)?\s*)?(?:a\s+)?"
        r"(?:delet\w*|eras\w*|remov\w*|clos\w*|destroy\w*|forget\w*|suppress\w*|"
        r"effac\w*|supprim\w*|elimin\w*|exclus\w*|borr\w*|apag\w*|retir\w*|"
        r"losch\w*|l?schen\w*|entfern\w*|cancell\w*)\b|"
        r"\bnot\s+(?:a\s+)?(?:request|asking|requesting|seeking)\s+(?:to|for)\s+"
        r"(?:delet\w*|eras\w*|remov\w*|clos\w*|destroy\w*|forget\w*|suppress\w*)\b|"
        r"\bne\s+(?:veux|souhait\w*|demand\w*|voudr\w*)\s+pas(?:\s+(?:de|la|le|les))?\s+"
        r"(?:delet\w*|eras\w*|remov\w*|supprim\w*|suppression\w*|effac\w*|elimin\w*)\b|"
        r"\bpas\s+(?:de|la|le|les)?\s*(?:delet\w*|eras\w*|remov\w*|supprim\w*|suppression\w*|effac\w*|elimin\w*)\b|"
        r"\bno\s+(?:quier\w*|quer\w*|solicit\w*|pido|deseo)\s+(?:que\s+)?(?:se\s+)?"
        r"(?:delet\w*|eras\w*|remov\w*|supprim\w*|elimin\w*|borr\w*|apag\w*)\b|"
        r"\bnao\s+(?:e|eh)\s+(?:uma?\s+)?(?:solicitacao|pedido)\s+de\s+"
        r"(?:delet\w*|eras\w*|remov\w*|exclus\w*|elimin\w*|apag\w*)\b|"
        r"\bno\s+(?:es\s+una\s+)?(?:solicitud|pedido|demande|request)\s+(?:de|to|for)\s+"
        r"(?:delet\w*|eras\w*|remov\w*|supprim\w*|elimin\w*|borr\w*)\b", re.I)
    nondelete = re.compile(
        r"\b(access|acces\w*|copy|copia|copie|send me|export|download|correct\w*|correction|"
        r"update|rectify|rectif\w*|corrig\w*|marketing|unsubscribe|opt[ -]?out|stop sending|"
        r"change|replace|keep|informacion|informacao|information request|solicitud de informacion)\b", re.I)
    object_re = re.compile(
        r"\b(my|me|personal|account|profile|records?|data|information|it|file|result|conta|"
        r"cuenta|datos|mis|mes|donnees|donn\w*|compte|konto)\b", re.I)
    request_re = re.compile(
        r"\b(please|i want|i would like|would like|i request|i am asking|i ask|requesting|"
        r"i am requesting|i exercise|can you|could you|kindly|right to|my right|demande|"
        r"demander|solicito|solicitar|solicite|intente|quiero|bitte|finish|complete|process|"
        r"permanently)\b", re.I)
    global_audit = bool(re.search(
        r"\b(please )?(check|verify|confirm|review|investigate|handle)\b.{0,150}\b"
        r"(account|profile|records?|data|traces?|identifiers?)\b", normalized)
        or re.search(r"\b(check|verify|confirm) (?:the )?(?:latest|current) state\b", normalized)
        or re.search(r"\b(profile is gone|remaining records? cannot identify me|left behind|still exists|find traces)\b", normalized))
    affirmative_data = bool(re.search(
        r"\b(?:delet\w*|eras\w*|remov\w*|destroy\w*|suppress\w*|exclus\w*|elimin\w*|"
        r"supprim\w*|borr\w*)\b.{0,60}\b(?:my|me|personal|account|profile|records?|data|"
        r"information|conta|cuenta|compte|konto|dados|datos|donnees)\b", normalized)
        or re.search(r"\b(?:my|me|personal|account|profile|records?|data|information|conta|cuenta|"
        r"compte|konto|dados|datos|donnees)\b.{0,60}\b(?:delet\w*|eras\w*|remov\w*|destroy\w*|"
        r"exclus\w*|elimin\w*|supprim\w*|borr\w*)\b", normalized))

    affirmative = False
    other_intent = False
    for clause in clauses:
        clause_negated = bool(negated_action.search(clause))
        if clause_negated:
            other_intent = True
            clause = negated_action.sub(" ", clause)
        if nondelete.search(clause) or re.search(
                r"\b(only need|only want|just want|keep (?:the|my|this) (?:account|profile|data))\b", clause):
            other_intent = True
        for match in action_re.finditer(clause):
            if clause_negated:
                continue
            left = clause[max(0, match.start()-80):match.start()]
            right = clause[match.end():match.end()+120]
            action = match.group(0).casefold()
            if action.startswith("clos") and not re.search(r"\b(account|profile|cuenta|compte|konto)\b", left+" "+right):
                continue
            marketing_only = (re.search(r"\b(marketing|promotional|mailing|email)\b", clause)
                and re.search(r"\b(list|messages?|emails?|marketing)\b", clause)
                and re.search(r"\b(only|unsubscribe|opt[ -]?out|stop)\b", clause)
                and not re.search(r"\b(?:delet|eras|destroy)\w*\b.{0,60}\b(my|personal|account|profile|records?|data|information)\b", clause))
            if not marketing_only and object_re.search(left+" "+right) and (request_re.search(clause) or match.start() < 12 or global_audit):
                affirmative = True
                break
    if affirmative or (global_audit and affirmative_data):
        return "DELETE"
    return "NOT_DELETION" if other_intent else "UNRESOLVED"

def authorizes_deletion(text: str) -> bool:
    """Compatibility wrapper for the intent regression evaluator."""
    return classify_intent(text) == "DELETE"


def _subject_values(case: dict[str, str], identities: Any) -> set[str]:
    values = set()
    for uid in identities.resolve(case.get("email", "")):
        for field in ("email", "name", "full_name", "phone", "email_hash", "user_id"):
            values |= identities.field_values(uid, field)
    return values


def _fact_values(fact: dict[str, Any]) -> set[str]:
    return {value.casefold() for values in fact.get("identifiers", {}).values() for value in values}


def _resource_source(fact: dict[str, Any]) -> str:
    # SQL table names distinguish primary and replica copies; otherwise system is the source.
    return str(fact.get("source") or fact.get("system") or "").casefold()


def latest_subject_resources(case: dict[str, str], facts: list[dict[str, Any]],
                             identities: Any) -> list[dict[str, Any]]:
    cutoff_facts = at_cutoff(facts, case["audit_at"])
    values = _subject_values(case, identities)
    seeds = [fact for fact in cutoff_facts
             if fact.get("resource_ids") and values & _fact_values(fact)]
    keys = {(_resource_source(fact), resource)
            for fact in seeds for resource in fact.get("resource_ids", []) if resource}
    latest = []
    for source, resource in sorted(keys):
        observations = [fact for fact in cutoff_facts
                        if resource in fact.get("resource_ids", [])
                        and _resource_source(fact) == source]
        if not observations:
            continue
        latest_at = max(parse_timestamp(fact["captured_at"]) for fact in observations)
        newest = [fact for fact in observations if parse_timestamp(fact["captured_at"]) == latest_at]
        # Some SQL records are indexed both as a row and as its nested JSON payload.
        # Merge those equal-time representations so an omitted field cannot contradict
        # the same row's explicit state. Distinct source/table keys remain separate.
        merged: dict[str, Any] = {
            "file_id": sorted({str(f.get("file_id", "")) for f in newest})[0],
            "file_ids": sorted({str(f.get("file_id", "")) for f in newest if f.get("file_id")}),
            "captured_at": newest[0]["captured_at"], "system": newest[0].get("system", ""),
            "source": newest[0].get("source"), "resource_ids": [resource],
            "identifiers": {}, "attributes": {}, "outcomes": [],
        }
        identifiers: dict[str, set[str]] = {}
        outcomes: set[str] = set()
        for fact in newest:
            merged["attributes"].update({k: v for k, v in fact.get("attributes", {}).items() if v is not None})
            for field, values_for_field in fact.get("identifiers", {}).items():
                identifiers.setdefault(field, set()).update(values_for_field)
            outcomes.update(str(x) for x in fact.get("outcomes", []))
        merged["identifiers"] = {k: sorted(v) for k, v in identifiers.items()}
        merged["outcomes"] = sorted(outcomes)
        latest.append(merged)
    return latest


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value or "").strip().casefold()
    if normalized in {"true", "1", "yes", "on", "enabled"}:
        return True
    if normalized in {"false", "0", "no", "off", "disabled", "blocked"}:
        return False
    return None


def _treatment(fact: dict[str, Any]) -> str:
    """Normalize observable resource state to compliant, violation, or unknown."""
    attrs = {str(k).casefold(): v for k, v in fact.get("attributes", {}).items()}
    text = " ".join(str(v).casefold() for v in attrs.values() if v is not None)
    outcomes = " ".join(str(v).casefold() for v in fact.get("outcomes", []))
    resource = " ".join(fact.get("resource_ids", [])).casefold()
    code = str(attrs.get("status_code", ""))
    result = str(attrs.get("result", "")).casefold()
    if code == "404" or "rows=0" in outcomes or result in {"not_found", "absent", "deleted"}:
        return "compliant"
    restore_allowed = _bool_value(attrs.get("restore_allowed"))
    if restore_allowed is False:
        return "compliant"
    if restore_allowed is True and resource.startswith("backup_"):
        return "violation"
    if resource.startswith("backup_"):
        return "violation"
    enabled = _bool_value(attrs.get("enabled"))
    if enabled is False or "stopped" in text or "disabled" in text or "blocked" in text:
        return "compliant"
    kind = str(attrs.get("record_type", attrs.get("data_category", ""))).casefold()
    event = str(attrs.get("event", "")).casefold()
    category = kind
    if not category:
        category = next((name for prefix, name in (
            ("account_", "user_profile"), ("search_", "search_index_entry"),
            ("analytics_", "analytics_profile"), ("support_", "support_message"),
            ("export_", "user_export"), ("audit_record_", "security_audit_log"),
            ("tombstone_", "account_tombstone"), ("backup_", "backup_archive"))
            if resource.startswith(prefix)), "")
    if resource.startswith("support_") and not kind:
        if "attachment" in event or attrs.get("file"):
            category = "support_attachment"
    action = _RULES.get(category, "")
    if action == "RETAIN":
        return "compliant"
    if action == "REDACT":
        pii = ("email", "name", "phone", "email_hash")
        return "violation" if any(fact.get("identifiers", {}).get(field) for field in pii) else "compliant"
    if action == "ANONYMIZE":
        return "violation" if any(fact.get("identifiers", {}).values()) else "compliant"
    if action == "DELETE":
        return "violation"
    if resource.startswith(("data_flow_", "sync_", "job_")):
        return "violation" if enabled is True else "unknown"
    if not action:
        # No supplied policy category means this fact cannot decide record treatment.
        return "unknown"
    if resource.startswith(("account_", "search_", "export_", "support_")):
        # A retained shared support conversation may keep a stable user reference, but not PII.
        if resource.startswith("support_") and not any(fact.get("identifiers", {}).get(k) for k in ("email", "name", "phone", "email_hash")):
            return "compliant"
        return "violation"
    if result in {"redacted", "anonymized", "blocked", "disabled", "retained"}:
        return "compliant"
    if result in {"found", "identifiable", "active", "present"} or "rows=1" in outcomes:
        return "violation"
    return "unknown"


def audit_status(case: dict[str, str], facts: list[dict[str, Any]], identities: Any) -> str:
    intent = classify_intent(case.get("request_text", ""))
    if intent == "NOT_DELETION":
        return "NOT_APPLICABLE"
    # Every row originates in the deletion workflow. Ambiguous intent therefore
    # falls back to a deletion audit and is recorded by main() for review.
    values = _subject_values(case, identities)
    if not values:
        return "INCOMPLETE"
    linked = latest_subject_resources(case, facts, identities)
    # A supported violation is sufficient for an incomplete verdict; operational activity
    # and reported workflow results are not used as state evidence.
    treatments = [_treatment(fact) for fact in linked]
    if "violation" in treatments:
        return "INCOMPLETE"
    # Absence from a full participant-visible SQL profile snapshot is a deterministic
    # account absence fact; linked, policy-compliant resources can establish a complete state.
    decided = [treatment for treatment in treatments if treatment != "unknown"]
    if decided and all(treatment == "compliant" for treatment in decided):
        return "COMPLETE"
    if not decided:
        allowed = {row["file_id"] for row in read_manifest()
                   if row["file_path"].casefold().endswith(".sql")
                   and parse_timestamp(row["captured_at"]) <= parse_timestamp(case["audit_at"])}
        facts_by_file: dict[str, list[dict[str, Any]]] = {}
        for fact in facts:
            if fact.get("file_id") in allowed:
                facts_by_file.setdefault(fact["file_id"], []).append(fact)
        if any(any(f.get("system") == "account_service" for f in rows) for rows in facts_by_file.values()):
            # A global SQL account snapshot with no row matching this user establishes absence
            # from that snapshot, but does not claim workflow or activity results as proof.
            return "COMPLETE"
    return "INCOMPLETE"


def build_rows(requests: list[dict[str, str]], facts: list[dict[str, Any]] | None = None,
               identities: Any | None = None) -> list[dict[str, str]]:
    facts = build_index() if facts is None else facts
    identities = load_index() if identities is None else identities
    result = []
    for request in sorted(requests, key=lambda row: row["case_id"]):
        status = audit_status(request, facts, identities)
        if status == "UNRESOLVED":
            # Last-resort deletion fallback: a workflow-submitted request must
            # never disappear from the output or emit an unsupported status.
            status = "INCOMPLETE"
        result.append({"case_id": request["case_id"], "deletion_status": status, "steps_json": "[]"})
    return result


def write_rows(rows: list[dict[str, str]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    requests = read_rows(DATASET / "deletion_requests.csv")
    flags = [
        {"case_id": request["case_id"], "original_intent": "UNRESOLVED", "fallback_intent": "DELETE"}
        for request in requests if classify_intent(request.get("request_text", "")) == "UNRESOLVED"
    ]
    rows = build_rows(requests)
    write_rows(rows, OUTPUT)
    flag_path = ROOT / "evaluation" / "unresolved_intent_flags.csv"
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    with flag_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "original_intent", "fallback_intent"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(flags, key=lambda row: row["case_id"]))
    print(f"Wrote {len(rows)} status-only rows to {OUTPUT}; steps_json is always [].")
    print(f"Recorded {len(flags)} unresolved-intent deletion fallbacks in {flag_path}.")


if __name__ == "__main__":
    main()
