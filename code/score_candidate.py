"""Score candidate steps on samples and extras, with compact mismatch diagnostics."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_index import build_index
from identity_resolution import load_index
import main as main_module
from main import DATASET, read_rows
from step_generation import build_candidate

FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def compare(label: str, requests: list[dict[str, str]], gold_rows: list[dict[str, str]],
            facts, identities) -> None:
    predicted = build_candidate(requests, facts, identities)
    gold_by = {row["case_id"]: row for row in gold_rows}
    pred_by = {row["case_id"]: row for row in predicted}
    exact_cases = step_total = step_correct = field_total = field_correct = 0
    categories: Counter[str] = Counter()
    examples: dict[str, str] = {}
    tuple_expected: set[tuple] = set()
    tuple_generated: set[tuple] = set()
    tuple_discovery: dict[str, set[tuple[str, str]]] = {}
    unmatched_expected: list[tuple[str, tuple]] = []
    tuple_matches = 0
    tuple_count_expected = tuple_count_generated = 0
    for case_id in sorted(gold_by):
        gs = json.loads(gold_by[case_id]["steps_json"])
        ps = json.loads(pred_by[case_id]["steps_json"])
        key = lambda s: (s["phase"], s["operation"], s["system_id"], s["resource_id"], s["state"])
        gtuples, ptuples = {key(s) for s in gs}, {key(s) for s in ps}
        tuple_expected.update((case_id, *t) for t in gtuples)
        tuple_generated.update((case_id, *t) for t in ptuples)
        tuple_count_expected += len(gtuples)
        tuple_count_generated += len(ptuples)
        tuple_matches += len(gtuples & ptuples)
        request = next(row for row in requests if row["case_id"] == case_id)
        linked = main_module.latest_subject_resources(request, facts, identities)
        tuple_discovery[case_id] = {(str(f.get("system", "")), r)
                                    for f in linked for r in f.get("resource_ids", [])}
        unmatched_expected.extend((case_id, t) for t in gtuples - ptuples)
        exact_cases += gs == ps
        n = max(len(gs), len(ps))
        step_total += n
        step_correct += sum(i < len(gs) and i < len(ps) and gs[i] == ps[i] for i in range(n))
        field_total += n * 7
        for i in range(n):
            g = gs[i] if i < len(gs) else None
            p = ps[i] if i < len(ps) else None
            if g is not None and p is not None:
                field_correct += sum(g.get(field) == p.get(field) for field in FIELDS)
                field_correct += g.get("step_no") == p.get("step_no")
            if g is None or p is None:
                name = "missing_predicted_step" if p is None else "extra_predicted_step"
                categories[name] += 1
                examples.setdefault(name, f"{case_id} step {i+1}")
                continue
            for field in FIELDS + ("step_no",):
                if g.get(field) != p.get(field):
                    categories[field] += 1
                    examples.setdefault(field, f"{case_id} step {i+1}: gold={g.get(field)!r}, predicted={p.get(field)!r}")
    print(f"{label}: cases={len(gold_by)}; step={step_correct}/{step_total} ({step_correct/step_total:.1%}); "
          f"field={field_correct}/{field_total} ({field_correct/field_total:.1%}); "
          f"sequence={exact_cases}/{len(gold_by)} ({exact_cases/len(gold_by):.1%})")
    for name, count in categories.most_common(5):
        print(f"  mismatch {name}: {count}; example {examples[name]}")
    precision = f"{tuple_matches/tuple_count_generated:.1%}" if tuple_count_generated else "n/a"
    recall = f"{tuple_matches/tuple_count_expected:.1%}" if tuple_count_expected else "n/a"
    print(f"  tuple precision={tuple_matches}/{tuple_count_generated} ({precision}); "
          f"recall={tuple_matches}/{tuple_count_expected} ({recall})")
    diagnosis: Counter[str] = Counter()
    diagnosis_examples: dict[str, str] = {}
    for case_id, item in unmatched_expected:
        _, operation, system, resource, state = item
        discovered = tuple_discovery[case_id]
        same_resource = {(s, r) for s, r in discovered if r == resource}
        generated_case = {tuple(x[1:]) for x in tuple_generated if x[0] == case_id}
        if (system, resource) not in discovered and same_resource:
            category = "d_wrong_system_attribution"
        elif any(t[0] == item[0] and t[2] == system and t[3] == resource and t[1] != operation or
                 t[0] == item[0] and t[2] == system and t[3] == resource and t[4] != state
                 for t in generated_case):
            category = "b_wrong_operation_or_state"
        elif (system, resource) not in discovered:
            category = "a_resource_not_discovered"
        else:
            category = "c_resource_discovered_step_omitted"
        diagnosis[category] += 1
        diagnosis_examples.setdefault(category, f"{case_id}: {item}")
    extras = tuple_generated - tuple_expected
    diagnosis["extra_generated_tuple"] += len(extras)
    if extras:
        case_id, *item = sorted(extras)[0]
        diagnosis_examples["extra_generated_tuple"] = f"{case_id}: {tuple(item)}"
    print("  unmatched expected tuples: " + ", ".join(f"{k}={v}" for k, v in diagnosis.items()))
    for category, example in diagnosis_examples.items():
        print(f"    {category} example: {example}")


def main() -> None:
    facts, identities = build_index(), load_index()
    compare("Public samples", read_rows(DATASET / "sample_deletion_requests.csv"),
            read_rows(DATASET / "sample_output.csv"), facts, identities)
    extra = ROOT / "evaluation" / "extra_cases"
    compare("Extra cases (separate)", read_rows(extra / "extra_requests.csv"),
            read_rows(extra / "extra_expected.csv"), facts, identities)


if __name__ == "__main__":
    main()
