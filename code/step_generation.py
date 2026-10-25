"""Evidence-backed remediation and verification step generation."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import main

PHASE_ORDER = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
OPERATION_ORDER = {
    "REPORT_REMAINING_RECORD": 0,
    "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2,
    "REPORT_RESTORE_RISK": 3,
    "DISABLE_DATA_FLOW": 0,
    "BLOCK_RESTORE": 1,
    "DELETE_RECORD": 2,
    "REDACT_RECORD": 3,
    "ANONYMIZE_RECORD": 4,
    "VERIFY_RECORD_ABSENT": 0,
    "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2,
    "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4,
    "VERIFY_RESTORE_BLOCKED": 5,
}


def category_for(fact: dict[str, Any]) -> str:
    attrs = {str(k).casefold(): v for k, v in fact.get("attributes", {}).items()}
    category = str(attrs.get("record_type", attrs.get("data_category", ""))).casefold()
    if category in main._RULES or category in {"data_flow", "sync_job", "import_job"}:
        return category
    file_hint = " ".join((str(fact.get("file_path", "")), str(attrs.get("file", "")))).casefold()
    if "attachment" in file_hint:
        return "support_attachment"
    resource = (fact.get("resource_ids") or [""])[0].casefold()
    return next((name for prefix, name in (
        ("account_", "user_profile"), ("search_", "search_index_entry"),
        ("analytics_", "analytics_profile"), ("support_", "support_message"),
        ("export_", "user_export"), ("audit_record_", "security_audit_log"),
        ("tombstone_", "account_tombstone"), ("backup_", "backup_archive"),
    ) if resource.startswith(prefix)), "")


def _step(phase: str, system: str, resource: str, operation: str,
          state: str, evidence_id: str) -> dict[str, Any]:
    return {"step_no": 0, "phase": phase, "system_id": system,
            "resource_id": resource, "operation": operation,
            "state": state, "evidence_id": evidence_id}


def _proof_fact(facts: list[dict[str, Any]], treatment: str | None = None) -> dict[str, Any]:
    candidates = [f for f in facts if f.get("file_id")]
    if treatment is not None:
        matching = [f for f in candidates if main._treatment(f) == treatment]
        if matching:
            candidates = matching
    return max(candidates, key=lambda f: (
        len(f.get("attributes", {})), len(f.get("identifiers", {})),
        str(f.get("captured_at", "")), str(f.get("file_id", ""))))


def policy_treatment(fact: dict[str, Any], category: str, action: str) -> str:
    """Apply the supplied category action to the latest observable fact."""
    attrs = {str(k).casefold(): v for k, v in fact.get("attributes", {}).items()}
    resource = (fact.get("resource_ids") or [""])[0].casefold()
    if resource.startswith(("data_flow_", "sync_", "job_")):
        if main._flow_can_copy(fact):
            return "violation"
        if main._bool_value(attrs.get("enabled")) is False or str(attrs.get("result", "")).casefold() == "disabled":
            return "compliant"
        return "unknown"
    if resource.startswith("backup_"):
        return "compliant" if main._bool_value(attrs.get("restore_allowed")) is False else "violation"
    result = str(attrs.get("result", attrs.get("status", ""))).casefold()
    absent = (str(attrs.get("status_code", "")) == "404"
              or result in {"not_found", "absent", "deleted"}
              or "rows=0" in {str(x).casefold() for x in fact.get("outcomes", [])})
    if action == "DELETE":
        return "compliant" if absent else "violation"
    identifiers = fact.get("identifiers", {})
    if action == "RETAIN":
        return "compliant"
    if action == "REDACT":
        direct = ("email", "name", "full_name", "phone", "email_hash")
        return "violation" if any(identifiers.get(field) for field in direct) else "compliant"
    if action == "ANONYMIZE":
        return "violation" if any(identifiers.values()) else "compliant"
    return "unknown"


def generate_steps(case: dict[str, str], status: str,
                   facts: list[dict[str, Any]], identities: Any) -> list[dict[str, Any]]:
    if status == "NOT_APPLICABLE":
        return []
    linked = main.latest_subject_resources(case, facts, identities)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in linked:
        for resource in fact.get("resource_ids", []):
            grouped[(str(fact.get("system", "")), resource)].append(fact)

    findings: list[dict[str, Any]] = []
    remediation: list[dict[str, Any]] = []
    verification: list[dict[str, Any]] = []

    for (system, resource), observations in grouped.items():
        category_values = {category_for(f) for f in observations}
        actions = {main._RULES.get(category, "") for category in category_values}
        treatment_values = {policy_treatment(f, category_for(f),
                                             main._RULES.get(category_for(f), ""))
                            for f in observations}
        violation = "violation" in treatment_values
        representative = _proof_fact(observations, "violation" if violation else None)
        evidence_id = str(representative.get("file_id", ""))
        category = category_for(representative)
        action = main._RULES.get(category, "")
        is_flow = resource.startswith(("data_flow_", "sync_", "job_"))
        is_backup = resource.startswith("backup_")

        if violation:
            if is_flow:
                findings.append(_step("FINDING", system, resource,
                                      "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", evidence_id))
                remediation.append(_step("REMEDIATION", system, resource,
                                         "DISABLE_DATA_FLOW", "DISABLED", ""))
            elif is_backup:
                findings.append(_step("FINDING", system, resource,
                                      "REPORT_RESTORE_RISK", "ACTIVE", evidence_id))
                remediation.append(_step("REMEDIATION", system, resource,
                                         "BLOCK_RESTORE", "BLOCKED", ""))
            elif action == "DELETE":
                findings.append(_step("FINDING", system, resource,
                                      "REPORT_REMAINING_RECORD", "PRESENT", evidence_id))
                remediation.append(_step("REMEDIATION", system, resource,
                                         "DELETE_RECORD", "ABSENT", ""))
            elif action in {"REDACT", "ANONYMIZE"}:
                findings.append(_step("FINDING", system, resource,
                                      "REPORT_EXPOSED_PII", "PRESENT", evidence_id))
                op, state = (("REDACT_RECORD", "REDACTED") if action == "REDACT"
                             else ("ANONYMIZE_RECORD", "ANONYMIZED"))
                remediation.append(_step("REMEDIATION", system, resource, op, state, ""))

        if is_flow:
            # Disabled flows are a required final state; enabled-but-unproven
            # connectors are outside the deletion category rules and get no step.
            disabled = any(main._bool_value((f.get("attributes") or {}).get("enabled")) is False
                           for f in observations)
            if violation or disabled:
                verification.append(_step("VERIFICATION", system, resource,
                                          "VERIFY_DATA_FLOW_DISABLED", "DISABLED",
                                          "" if status == "INCOMPLETE" else evidence_id))
            continue
        if is_backup:
            restore_blocked = any(main._bool_value((f.get("attributes") or {}).get("restore_allowed")) is False
                                  for f in observations)
            if violation or restore_blocked:
                verification.append(_step("VERIFICATION", system, resource,
                                          "VERIFY_RESTORE_BLOCKED", "BLOCKED",
                                          "" if status == "INCOMPLETE" else evidence_id))
            continue

        if action == "DELETE":
            op, state = "VERIFY_RECORD_ABSENT", "ABSENT"
        elif action == "RETAIN":
            op, state = "VERIFY_RECORD_PRESENT", "PRESENT"
        elif action == "REDACT":
            op, state = "VERIFY_RECORD_REDACTED", "REDACTED"
        elif action == "ANONYMIZE":
            op, state = "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"
        else:
            # Categories without a supplied deletion rule are deliberately omitted.
            continue
        verification.append(_step("VERIFICATION", system, resource, op, state,
                                  "" if status == "INCOMPLETE" else evidence_id))

    # A global account snapshot can prove absence without an extant resource ID.
    # Use the evidence file and its observed system, leaving resource_id empty.
    if status == "COMPLETE" and not verification:
        cutoff = main.parse_timestamp(case["audit_at"])
        permitted = {r["file_id"] for r in main.read_manifest()
                     if r["file_path"].casefold().endswith(".sql")
                     and main.parse_timestamp(r["captured_at"]) <= cutoff}
        account_snapshot = next((f for f in facts if f.get("file_id") in permitted
                                 and f.get("system") == "account_service" and f.get("file_id")), None)
        if account_snapshot:
            verification.append(_step("VERIFICATION", "account_service", "",
                                      "VERIFY_RECORD_ABSENT", "ABSENT",
                                      str(account_snapshot["file_id"])))

    phase_steps = findings + remediation + verification
    deduplicated: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for step in phase_steps:
        key = (step["phase"], step["system_id"], step["resource_id"],
               step["operation"], step["state"])
        prior = deduplicated.get(key)
        if prior is None or (not prior["evidence_id"] and step["evidence_id"]):
            deduplicated[key] = step
    ordered = sorted(deduplicated.values(), key=lambda s: (
        PHASE_ORDER[s["phase"]], OPERATION_ORDER[s["operation"]],
        s["system_id"], s["resource_id"]))
    for number, step in enumerate(ordered, start=1):
        step["step_no"] = number
    return ordered


def build_candidate(requests: list[dict[str, str]], facts: list[dict[str, Any]],
                    identities: Any) -> list[dict[str, str]]:
    rows = []
    for case in sorted(requests, key=lambda row: row["case_id"]):
        status = main.audit_status(case, facts, identities)
        steps = generate_steps(case, status, facts, identities)
        rows.append({"case_id": case["case_id"], "deletion_status": status,
                     "steps_json": json.dumps(steps, ensure_ascii=False, separators=(",", ":"))})
    return rows
