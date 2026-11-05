# Phase 05 efficiency and evaluation protocol

Date: 2026-11-06. Research prototype; no clinical validation claim.

## Measured assembly improvement

Compared the original assembler from commit `5244682` with the time-window
implementation on the same Windows/Python 3.12 machine, deterministic authored
fixtures, identical cutoff and five repetitions per size. Full Episode objects
and skipped counts matched before timing. Medians:

| Meals | Input events | Before (ms) | After (ms) | Speedup |
| --- | --- | --- | --- | --- |
| 80 | 2,080 | 64.85 | 39.07 | 1.66x |
| 200 | 5,200 | 273.24 | 102.49 | 2.67x |
| 1,000 | 26,000 | 5,349.75 | 522.08 | 10.25x |

The final row is an offline stress case exceeding the live 5,000-CGM-per-kind
limit. None of these timings includes database, API, network or graph work.
Hardware load affects timings; this is an observed comparison, not a latency SLA.
Raw comparison and preserved baseline are in the local task work directory,
`D:/Archit/Others/t1d-metabolic-work/work/phase05-efficiency`.

Reproduce current-version timing from the repository root:

```powershell
uv run python scripts/benchmark_memory.py --meals 80 200 1000 --repeats 5
```

Binary search selects inclusive context/response windows instead of scanning
the complete history for every meal. Revision resolution, source ordering,
identity hashing, missingness, overlapping-meal warnings and canonical checks
are retained. There is no persistent cache to bypass revocation.

Canonical reads use batches of at most 500 records with approved-source checks,
scoped payload reads and batched meal components/nutrients. For one and 24 meals
with 25 CGM records each, regression tests assert 26 and 28 SQL statements,
including all four kind-history authorization checks. The previous code's
corresponding statement counts were 74 and 1,316 by inspection. The new counts
passed actual PostgreSQL tests on commit `f104f0c` (56 integration tests overall). These counts
cover one canonical-adapter call, not an entire retrieval; retrieval deliberately
calls the adapter twice to detect changes after derived search.

## Independent judgments and reproducibility

`scripts/evaluate_memory.py` retains the simple synthetic food-overlap comparison
and adds an offline judged-benchmark format. Export fictional input and its schema
outside the repository; do not commit research records or real health data:

```powershell
uv run python scripts/evaluate_memory.py --export-template D:/Archit/Others/t1d-metabolic-work/work/phase05-efficiency/template.json --export-schema D:/Archit/Others/t1d-metabolic-work/work/phase05-efficiency/schema.json
uv run python scripts/evaluate_memory.py --judged-input D:/Archit/Others/t1d-metabolic-work/work/phase05-efficiency/template.json
```

The template is synthetic and is not independent expert evidence. It explicitly
simulates incremental materialization one second after each response window;
live database materialization remains server-stamped and cannot be backdated.

For an authorized real research evaluation, supply a reviewed, frozen snapshot
with `data_kind=permitted-research`, `judgment_method=independent-review`, a dataset
version, protocol version, immutable episodes and held-out queries. The evaluator
does not acquire data or verify permissions/assessor qualifications. It checks:

- Unique episode/query identities and complete binary judgments for every
  eligible candidate, including explicit nonrelevance; missing labels are refused.
- Same study/patient, known-by-cutoff availability, completed response windows,
  source availability and exclusion of the query's anchor meal.
- Identical eligible pools and queries across structured, vector and hybrid
  profiles; relevance comes from supplied judgments, never from ranking scores.

Reports include an input SHA-256, precision/recall/nDCG@k, reciprocal rank,
equal-patient macro means and paired differences versus structured retrieval.
Seeded 1,000-resample patient-cluster bootstrap intervals preserve within-patient
query dependence. With only one patient, confidence intervals are explicitly
unavailable. Small patient cohorts still give unreliable uncertainty estimates.
Queries without relevant history score zero and are counted, rather than omitted.
The input is bounded to 20 MB, 5,000 episodes and 1,000 queries for offline use.

Profile timing now excludes feature preparation and computes only the components
used by each profile. Historical embeddings are reused within this immutable
offline run. This corrects the earlier benchmark's unnecessary vector/graph work
for structured retrieval. Earlier latency values are not directly comparable.

## Evidence still required

Before claiming a strong research result, freeze relevance criteria and primary
metrics before looking at held-out outcomes. Have qualified independent reviewers
label cases blind to model rankings and document disagreement/adjudication. Use
permitted data across enough independent patients, with chronological queries;
never tune on held-out judgments. Any trained encoder additionally needs separate
patient-disjoint training/validation/test provenance and a licensing/version
manifest. The current deterministic hash baseline trains on no patient data.

Evaluate sparse/dense histories, missing-context cases and food categories, and
report uncertainty and failure rates separately. Benchmark full API latency and
resource use at realistic workload/concurrency beyond these assembly timings.
Only subsequent Phase 06 comparisons can establish forecast benefit. Graph food
overlap and hashed food features are related signals, not independent clinical
evidence. The harness provides better experiments; it does not manufacture
independent labels, semantic understanding, external validity or higher accuracy.
