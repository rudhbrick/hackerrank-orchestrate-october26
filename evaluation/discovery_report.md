# Public sample evidence discovery

Metrics cover exactly the 32 rows in `sample_deletion_requests.csv`; extra requests and overlay facts are excluded.

- Case-scoped pairs: TP 74, FP 1, FN 37
- Recall: 74/111 = 66.7%
- Precision: 74/75 = 98.7%

## Evidence-type breakdown

Each type is independently compared against the full set of expected case-scoped pairs.

| Type | Discovered pairs | TP | FP | FN | Recall | Precision |
|---|---:|---:|---:|---:|---:|---:|
| JSON | 30 | 30 | 0 | 81 | 27.0% | 100.0% |
| LOG | 23 | 22 | 1 | 89 | 19.8% | 95.7% |
| SQL | 8 | 8 | 0 | 103 | 7.2% | 100.0% |
| TXT | 13 | 13 | 0 | 98 | 11.7% | 100.0% |
| PDF | 1 | 1 | 0 | 110 | 0.9% | 100.0% |
| PNG | 0 | 0 | 0 | 111 | 0.0% | n/a |

## Misses by cause

Each expected (system, resource) pair is counted once per case.

| Cause | Count |
|---|---:|
| identifier not matched | 15 |
| activity-only record | 14 |
| cutoff exclusion | 4 |
| no participant evidence | 4 |
| resource-field/format gap | 0 |
| needs image | 0 |
| other | 0 |

## Cause-category changes

Counts compare the earlier extractor with the generalized parser changes in this run. The identifier-link fixes are deterministic and use record-local fields, explicit trace IDs, pages, or delimited rows.

| Cause | Before | After | Change | General handling |
|---|---:|---:|---:|---|
| identifier not matched | 44 | 15 | -29 | Parse identity-reference aliases and nested JSON; join identifiers only within structured records, trace IDs, pages, or delimited rows. Applied. |
| activity-only record | 13 | 14 | +1 | Use activity only when it carries an explicit subject identifier; result claims alone cannot establish a subject link. No safe link was available for these remaining misses. |
| cutoff exclusion | 6 | 4 | -2 | Parse timestamps robustly, then exclude facts after audit_at. Later evidence remains excluded. |
| no participant evidence | 3 | 4 | +1 | No deterministic source identifies the target by cutoff; leave unresolved. |
| resource-field/format gap | 1 | 0 | -1 | Recognize generic resource-reference column aliases and row layouts. Applied. |
| needs image | 0 | 0 | 0 | No missed pair required image parsing. |
| other | 0 | 0 | 0 | No remaining pair fell outside these causes. |

The 18 extras in the earlier report were reviewed: 17 were instance/pod metadata tokens mistakenly treated as resources (decoys); one was a resource lookup with 0 rows and HTTP 404, legitimately omitted by the sample answer. None were duplicate case-scoped pairs.


## Misses

Each listed pair includes its generic cause.

- `case_01`: `account_service/account_001` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.
- `case_02`: `account_service/account_002` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.
- `case_03`: `analytics_platform/analytics_9406` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_04`: `account_service/account_004` [no participant evidence] No indexed participant evidence identifies this resource by audit_at; it may be an absence or retention target.; `analytics_platform/analytics_901` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_07`: `account_service/account_007` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.
- `case_08`: `account_service/account_008` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.
- `case_09`: `account_service/account_3960` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.; `security_service/audit_record_4902` [no participant evidence] No indexed participant evidence identifies this resource by audit_at; it may be an absence or retention target.
- `case_10`: `account_service/account_010` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.
- `case_16`: `search_service/search_1007` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_18`: `account_service/account_5521` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.; `security_service/audit_record_6645` [no participant evidence] No indexed participant evidence identifies this resource by audit_at; it may be an absence or retention target.
- `case_20`: `account_service/account_5037` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.; `security_service/audit_record_5569` [no participant evidence] No indexed participant evidence identifies this resource by audit_at; it may be an absence or retention target.
- `case_21`: `account_service/account_6440` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.; `analytics_platform/analytics_5335` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_22`: `account_service/account_4990` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.; `search_service/search_8911` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_23`: `account_service/account_410` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.; `security_service/audit_record_4128` [cutoff exclusion] Matching resource evidence is captured after audit_at and is correctly excluded.
- `case_24`: `account_service/account_5334` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.; `security_service/audit_record_7095` [cutoff exclusion] Matching resource evidence is captured after audit_at and is correctly excluded.
- `case_25`: `account_service/account_3136` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.; `analytics_platform/analytics_1895` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_26`: `account_service/account_5684` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.; `analytics_platform/analytics_4566` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_27`: `account_service/account_3866` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.; `analytics_platform/analytics_4574` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_28`: `account_service/account_5482` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.; `analytics_platform/analytics_6077` [identifier not matched] The resource is parsed before cutoff, but the same fact lacks a subject identifier.
- `case_29`: `account_service/account_7012` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.; `security_service/audit_record_3954` [cutoff exclusion] Matching resource evidence is captured after audit_at and is correctly excluded.
- `case_30`: `account_service/account_4163` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.; `security_service/audit_record_1707` [cutoff exclusion] Matching resource evidence is captured after audit_at and is correctly excluded.
- `case_31`: `account_service/account_4857` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.
- `case_32`: `account_service/account_8858` [activity-only record] The resource appears only in activity rows; those rows do not establish a subject link or resulting state.

## Extras

Each listed pair was discovered from a subject-matching fact but is absent from that case's sample answer.

- `case_17`: `account_service/account_6523` (evidence_67; LOG) — sample legitimately omits: lookup outcome is 0 rows/404

## Extra-case isolation

Extra requests are excluded from the 32-sample metrics. Overlay facts, when explicitly loaded, are reported separately and never merged into headline metrics.
- No overlay loaded (no `--overlay` supplied); overlay and extra-case files did not enter sample discovery.
