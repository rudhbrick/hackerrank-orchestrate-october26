"""Explain missing sample verification tuples using participant-facing facts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main
from evidence_index import build_index
from identity_resolution import load_index
from main import DATASET, _fact_values, _subject_values, read_rows
from step_generation import build_candidate, category_for
from timestamps import parse_timestamp


def main_fn() -> None:
    requests = read_rows(DATASET / "sample_deletion_requests.csv")
    gold = {r["case_id"]: r for r in read_rows(DATASET / "sample_output.csv")}
    facts, identities = build_index(), load_index()
    generated = {r["case_id"]: r for r in build_candidate(requests, facts, identities)}
    target_ops = {"VERIFY_RECORD_ANONYMIZED", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_ABSENT"}
    for case in requests:
        case_id = case["case_id"]
        expected = [s for s in json.loads(gold[case_id]["steps_json"])
                    if s["operation"] in target_ops]
        predicted = {tuple(s.get(k) for k in ("phase", "operation", "system_id", "resource_id", "state"))
                     for s in json.loads(generated[case_id]["steps_json"])}
        for step in expected:
            key = tuple(step.get(k) for k in ("phase", "operation", "system_id", "resource_id", "state"))
            if key in predicted:
                continue
            resource = step["resource_id"]
            cutoff = parse_timestamp(case["audit_at"])
            subject_values = _subject_values(case, identities)
            uid_set = identities.resolve(case["email"])
            print(f"{case_id}\t{step['operation']}\t{step['system_id']}\t{resource}")
            hits = [f for f in facts if resource in f.get("resource_ids", [])]
            if not hits:
                print("  NO_FACT")
                continue
            for fact in hits:
                values = _fact_values(fact)
                direct = bool(values & subject_values)
                after_cutoff = parse_timestamp(fact["captured_at"]) > cutoff
                linked = False
                for uid in uid_set:
                    if any(values & identities.field_values(uid, field)
                           for field in ("email", "name", "full_name", "phone", "email_hash", "user_id")):
                        linked = True
                attrs = fact.get("attributes", {})
                subject_ref = attrs.get("subject_reference", attrs.get("customer_reference", ""))
                category = category_for(fact)
                action = main._RULES.get(category, "")
                discovered = any(resource in x.get("resource_ids", [])
                                 and x.get("system") == step["system_id"]
                                 for x in main.latest_subject_resources(case, facts, identities))
                reason = ("cutoff" if after_cutoff else "not_linked" if not linked
                          else "missing_rule_mapping" if not action else "generator_logic")
                print("  ", {"file_id": fact.get("file_id"), "captured_at": fact.get("captured_at"),
                       "system": fact.get("system"), "source": fact.get("source"),
                       "resource_id": resource, "identifiers": fact.get("identifiers", {}),
                       "subject_reference": subject_ref, "category": category, "action": action,
                       "direct_subject_identifier": direct, "linked_by_identity": linked,
                       "after_cutoff": after_cutoff, "discovered": discovered, "reason": reason,
                       "attributes": attrs})


if __name__ == "__main__":
    main_fn()
