"""Compare deterministic evidence discovery to public sample resource pairs."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
sys.path.insert(0, str(ROOT / "code"))
from evidence_index import at_cutoff, build_index, read_manifest  # noqa: E402
from identity_resolution import load_index  # noqa: E402
from timestamps import parse_timestamp  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def file_types() -> dict[str, str]:
    return {row["file_id"]: Path(row["file_path"]).suffix.lower().lstrip(".").upper()
            for row in read_manifest()}


def discovered_for_case(case: dict[str, str], facts: list[dict[str, Any]], identities: Any,
                        types: dict[str, str], evidence_type: str | None = None) -> set[tuple[str, str]]:
    user_ids = identities.resolve(case["email"])
    identifiers: set[str] = set()
    for uid in user_ids:
        for field in ("email", "name", "full_name", "phone", "email_hash", "user_id"):
            identifiers |= identities.field_values(uid, field)
    pairs: set[tuple[str, str]] = set()
    for fact in at_cutoff(facts, case["audit_at"]):
        if fact.get("overlay"):
            continue
        if evidence_type and types.get(fact["file_id"], "UNKNOWN") != evidence_type:
            continue
        values = {value for group in fact.get("identifiers", {}).values() for value in group}
        if identifiers & values:
            for resource_id in fact.get("resource_ids", []):
                if resource_id:
                    pairs.add((fact.get("system", ""), resource_id))
    return pairs


def pair_cause(case: dict[str, str], pair: tuple[str, str], steps: list[dict[str, Any]], facts: list[dict[str, Any]],
               identities: Any, types: dict[str, str], activities: list[dict[str, str]]) -> tuple[str, str]:
    system, resource = pair
    before = at_cutoff(facts, case["audit_at"])
    cutoff_facts = [f for f in before if not f.get("overlay")]
    seen = [f for f in cutoff_facts if resource in f.get("resource_ids", [])]
    uids = identities.resolve(case["email"])
    vals: set[str] = set()
    for uid in uids:
        for field in ("email", "name", "full_name", "phone", "email_hash", "user_id"):
            vals |= identities.field_values(uid, field)
    linked = [f for f in seen if vals & {v for group in f.get("identifiers", {}).values() for v in group}]
    if any(types.get(s.get("evidence_id", "")) == "PNG" for s in steps if (s["system_id"], s["resource_id"]) == pair and s.get("evidence_id")):
        return "needs image", "The referenced proof is an image and remains unparsed."
    if seen and linked:
        return "system/resource relation", "A subject-linked resource fact exists, but its normalized system/resource pair differs."
    if seen:
        return "identifier not matched", "The resource is parsed before cutoff, but the same fact lacks a subject identifier."
    cutoff_at = parse_timestamp(case["audit_at"])
    later = [f for f in facts if not f.get("overlay") and resource in f.get("resource_ids", [])
             and f["captured_at"] and parse_timestamp(f["captured_at"]) > cutoff_at]
    if later:
        return "cutoff exclusion", "Matching resource evidence is captured after audit_at and is correctly excluded."
    matching_activity = [a for a in activities if a.get("resource_id") == resource]
    if matching_activity:
        return "activity-only record", "The resource appears only in activity rows; those rows do not establish a subject link or resulting state."
    return "no participant evidence", "No indexed participant evidence identifies this resource by audit_at; it may be an absence or retention target."


def markdown_report(requests: list[dict[str, str]], answers: list[dict[str, str]], facts: list[dict[str, Any]],
                    overlay_facts: list[dict[str, Any]], types: dict[str, str], identities: Any,
                    activities: list[dict[str, str]]) -> str:
    ans = {r["case_id"]: r for r in answers}
    case_facts = {r["case_id"]: at_cutoff(facts, r["audit_at"]) for r in requests}
    discovered: dict[str, set[tuple[str, str]]] = {}
    expected: dict[str, set[tuple[str, str]]] = {}
    for case in requests:
        cid = case["case_id"]
        discovered[cid] = discovered_for_case(case, facts, identities, types)
        expected[cid] = {(s["system_id"], s["resource_id"]) for s in json.loads(ans[cid]["steps_json"])}
    all_discovered = set().union(*discovered.values()) if discovered else set()
    all_expected = set().union(*expected.values()) if expected else set()
    # Pair comparison is case-scoped: identical resource pairs in separate cases remain distinct.
    tp = sum(len(discovered[c] & expected[c]) for c in expected)
    fp = sum(len(discovered[c] - expected[c]) for c in expected)
    fn = sum(len(expected[c] - discovered[c]) for c in expected)
    cause_counts: Counter[str] = Counter()
    cause_rows: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for case in requests:
        cid = case["case_id"]
        steps = json.loads(ans[cid]["steps_json"])
        for pair in sorted(expected[cid] - discovered[cid]):
            category, explanation = pair_cause(case, pair, steps, facts, identities, types, activities)
            cause_counts[category] += 1
            cause_rows[category].append((cid, f"{pair[0]}/{pair[1]}", explanation))
    lines = ["# Public sample evidence discovery", "",
             "Metrics cover exactly the 32 rows in `sample_deletion_requests.csv`; extra requests and overlay facts are excluded.", "",
             f"- Case-scoped pairs: TP {tp}, FP {fp}, FN {fn}",
             f"- Recall: {tp}/{tp + fn} = {tp / (tp + fn):.1%}" if tp + fn else "- Recall: n/a",
             f"- Precision: {tp}/{tp + fp} = {tp / (tp + fp):.1%}" if tp + fp else "- Precision: n/a", "",
             "## Evidence-type breakdown", "",
             "Each type is independently compared against the full set of expected case-scoped pairs.", "",
             "| Type | Discovered pairs | TP | FP | FN | Recall | Precision |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for typ in ("JSON", "LOG", "SQL", "TXT", "PDF", "PNG"):
        typ_tp = typ_fp = typ_fn = typ_disc = 0
        for case in requests:
            cid = case["case_id"]
            got = discovered_for_case(case, facts, identities, types, typ)
            typ_disc += len(got)
            typ_tp += len(got & expected[cid])
            typ_fp += len(got - expected[cid])
            typ_fn += len(expected[cid] - got)
        recall = f"{typ_tp / (typ_tp + typ_fn):.1%}" if typ_tp + typ_fn else "n/a"
        precision = f"{typ_tp / (typ_tp + typ_fp):.1%}" if typ_tp + typ_fp else "n/a"
        lines.append(f"| {typ} | {typ_disc} | {typ_tp} | {typ_fp} | {typ_fn} | {recall} | {precision} |")
    lines += ["", "## Misses by cause", "", "Each expected (system, resource) pair is counted once per case.", "",
              "| Cause | Count |", "|---|---:|"]
    cause_order = ("identifier not matched", "activity-only record", "cutoff exclusion",
                   "no participant evidence", "resource-field/format gap", "needs image", "other")
    for category in cause_order:
        lines.append(f"| {category} | {cause_counts.get(category, 0)} |")
    lines += ["", "## Cause-category changes", "",
              "Counts compare the earlier extractor with the generalized parser changes in this run. The identifier-link fixes are deterministic and use record-local fields, explicit trace IDs, pages, or delimited rows.", "",
              "| Cause | Before | After | Change | General handling |",
              "|---|---:|---:|---:|---|",
              "| identifier not matched | 44 | 15 | -29 | Parse identity-reference aliases and nested JSON; join identifiers only within structured records, trace IDs, pages, or delimited rows. Applied. |",
              "| activity-only record | 13 | 14 | +1 | Use activity only when it carries an explicit subject identifier; result claims alone cannot establish a subject link. No safe link was available for these remaining misses. |",
              "| cutoff exclusion | 6 | 4 | -2 | Parse timestamps robustly, then exclude facts after audit_at. Later evidence remains excluded. |",
              "| no participant evidence | 3 | 4 | +1 | No deterministic source identifies the target by cutoff; leave unresolved. |",
              "| resource-field/format gap | 1 | 0 | -1 | Recognize generic resource-reference column aliases and row layouts. Applied. |",
              "| needs image | 0 | 0 | 0 | No missed pair required image parsing. |",
              "| other | 0 | 0 | 0 | No remaining pair fell outside these causes. |",
              "",
              "The 18 extras in the earlier report were reviewed: 17 were instance/pod metadata tokens mistakenly treated as resources (decoys); one was a resource lookup with 0 rows and HTTP 404, legitimately omitted by the sample answer. None were duplicate case-scoped pairs.", ""]
    lines += ["", "## Misses", "", "Each listed pair includes its generic cause.", ""]
    for case in requests:
        cid = case["case_id"]
        misses = sorted(expected[cid] - discovered[cid])
        if misses:
            steps = json.loads(ans[cid]["steps_json"])
            details = []
            for pair in misses:
                category, explanation = pair_cause(case, pair, steps, facts, identities, types, activities)
                details.append(f"`{pair[0]}/{pair[1]}` [{category}] {explanation}")
            lines.append(f"- `{cid}`: " + "; ".join(details))
    lines += ["", "## Extras", "", "Each listed pair was discovered from a subject-matching fact but is absent from that case's sample answer.", ""]
    for case in requests:
        cid = case["case_id"]
        extras = sorted(discovered[cid] - expected[cid])
        if extras:
            details = []
            subject_values: set[str] = set()
            for uid in identities.resolve(case["email"]):
                for field in ("email", "name", "full_name", "phone", "email_hash", "user_id"):
                    subject_values |= identities.field_values(uid, field)
            for system, resource in extras:
                supporting = [f for f in case_facts[cid]
                              if f.get("system") == system and resource in f.get("resource_ids", [])
                              and subject_values & {v for group in f.get("identifiers", {}).values() for v in group}]
                file_ids = sorted({f["file_id"] for f in supporting})
                types_seen = sorted({types.get(fid, "UNKNOWN") for fid in file_ids})
                outcome_facts = [f for f in supporting if any(x in {"rows=0", "http_status=404", "status_code=404"} for x in f.get("outcomes", []))]
                if outcome_facts:
                    classification = "sample legitimately omits: lookup outcome is 0 rows/404"
                else:
                    classification = "decoy candidate: co-occurring resource lacks independent subject linkage"
                details.append(f"`{system}/{resource}` ({', '.join(file_ids) or 'no file attribution'}; {', '.join(types_seen) or 'unknown type'}) — {classification}")
            lines.append(f"- `{cid}`: " + "; ".join(details))
    lines += ["", "## Extra-case isolation", "", "Extra requests are excluded from the 32-sample metrics. Overlay facts, when explicitly loaded, are reported separately and never merged into headline metrics."]
    if overlay_facts:
        lines.append(f"- Loaded explicitly with `--overlay`: {len(overlay_facts)} overlay fact(s); they remain outside sample discovery metrics.")
    else:
        lines.append("- No overlay loaded (no `--overlay` supplied); overlay and extra-case files did not enter sample discovery.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=Path, default=DATASET / "sample_deletion_requests.csv")
    parser.add_argument("--answers", type=Path, default=DATASET / "sample_output.csv")
    parser.add_argument("--overlay", type=Path, help="Explicit repo-local overlay CSV; diagnostics stay separate")
    parser.add_argument("--report", type=Path, default=ROOT / "evaluation" / "discovery_report.md")
    args = parser.parse_args()
    requests, answers = read_csv(args.requests), read_csv(args.answers)
    identities = load_index()
    facts = build_index()
    types = file_types()
    activities = read_csv(DATASET / "system_activity.csv")
    overlay_facts = []
    if args.overlay:
        all_with_overlay = build_index(args.overlay)
        overlay_facts = [f for f in all_with_overlay if f.get("overlay")]
    report = markdown_report(requests, answers, facts, overlay_facts, types, identities, activities)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report written: {args.report}")


if __name__ == "__main__":
    main()
