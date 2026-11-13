# Phase 08 regression report

The approved synthetic engineering scope exercises the safety gate on the
protected forecast route and in the local Phases 05–07 workflow. The
end-to-end HTTP test submits a confirmed meal revision through the production
meal route, retrieves historical evidence through the production memory route,
and obtains Phase 06 forecasts through the production forecast route. The
Phase 07 demo consumes the typed retrieval response and checks it against
the scoped canonical episode before including it. Tests use fictional
records and fixture-backed database I/O.

## Tested scenarios

| Scenario | Observed behavior |
| --- | --- |
| Confirmed meal, fresh CGM and completed personal history | Four horizons for the base, personalized and memory-assisted comparisons |
| Confirmed meal and fresh CGM with no personal history | Four baseline horizons with explicit cold status and missing history |
| Draft meal | Abstention before forecast display |
| Stale CGM | Abstention using the existing synthetic Phase 06 freshness rule |
| Memory dependency unavailable | Abstention and no forecast data |
| Foreign, late, or altered evidence | Evidence rejected before personalization |
| Late or foreign feedback | Same forecast and input fingerprint as the original cutoff |
| Corrupt, incomplete, or mis-timed model output | Final gate blocks the payload |
| Canonical readings change during inference | Protected request fails with a redacted unavailable response |
| Audit write fails | Forecast withheld |
| Retry after grant revocation | Scope rechecked and request denied before CGM access |
| Unapproved simulation request | Route unavailable |

All 21 dedicated Phase 08 tests passed. This exercise uses the same technical
five-minute freshness and cadence policy as the existing synthetic Phase 06
service. The final gate checks the output contract without introducing
clinical alert, intervention, or uncertainty-width thresholds.

## Paired workflow comparison

Eight fictional forecast cutoffs had complete results in all three arms.
Mean absolute error in mg/dL is shown to verify paired scoring, input
alignment, and traceability for future research comparisons.

| Method | 30 min | 60 min | 90 min | 120 min |
| --- | ---: | ---: | ---: | ---: |
| Phase 06 | 3.81 | 7.58 | 9.25 | 11.06 |
| Phase 07 | 3.80 | 7.42 | 9.07 | 11.20 |
| Phase 07 with retrieved meals | 4.02 | 7.79 | 9.46 | 11.19 |

These authored scenarios verify plumbing and abstention. The Phase 07
independent cohort evaluation remains the evidence for forecast quality
with observed CGM. [Phase 07 validation](../phase-07-personalization/INDEPENDENT_VALIDATION.md)

## Acceptance and residual work

- **SAFE-001, SAFE-002, SAFE-006, SAFE-007.** The forecast and demo return
  glucose, ranges, and research metadata. Simulation and treatment actuation
  are outside the exposed route set. Qualified review of any future insulin
  estimate is part of the deferred simulation protocol.
- **SAFE-003, SAFE-004.** Existing input/source checks and the final output
  gate are exercised through the protected route. The workflow checks
  evidence availability and identity. No-store responses, a retry
  after revocation, changed-input rejection and audit failure are covered.
  The current workflow is synchronous and has no result cache or worker.
- **SAFE-005, SAFE-008.** Outputs carry experimental and review-required
  flags, assumptions, missingness, interval bounds and lineage. Personalized
  synthetic demo intervals are illustrative. Previous domain-shift evidence
  shows the residual risk of undercoverage.
- **SAFE-009, SAFE-010.** Emergency copy and production privacy qualification
  remain part of the reviewed frontend and deployment work. The regression
  suite checks redacted service failures and scoped output handling.

### Hazard review

| Risk register entries | Phase 08 evidence | Remaining qualification |
| --- | --- | --- |
| R-001, R-002, R-003 | Confirmed synthetic meal revision, observed CGM freshness, explicit missing insulin and activity | Real source and context review |
| R-004 | Ordered intervals, exact horizons, cutoff-relative timestamps, published coverage limitations | Clinically reviewed applicability and uncertainty policy |
| R-005, R-007 | Scoped canonical reconstruction, foreign and late evidence probes, no-store response and retry reauthorization | Real-store, frontend and deployment verification |
| R-006, R-010 | Research-only output and review flags, simulation route probe and deferral | Independent qualified protocol review |
| R-008 | Artifact checksums, changed readings, malformed outputs and failed audit handling | Disposable real-store run on a host with Docker |
| R-009 | The demo consumes typed meal and retrieval data only | Vision and upload qualification remain in their existing scope |

### Clinical simulation deferral

The roadmap allows an explicit deferral when an independently approved
clinical protocol is absent. The deferral applies to simulation execution,
clinical definitions, insulin estimates and treatment review. To reopen it,
a qualified clinician must provide a versioned protocol, verified setting
requirements, uncertainty assumptions, reviewer roles and output restrictions.

### Verification record

- `python -m pytest -q phases/phase-08-safety/tests` passed all 21 tests.
- The focused Phase 05–08 suite plus forecast and memory API regressions
  passed all 137 tests.
- `python -m pytest -q --ignore=tests/integration` reported 256 passes
  and two existing Windows vision failures. The symlink test requires a
  Windows privilege and the supervision test fails during Windows pipe
  cleanup.
- Ruff lint and formatting, strict mypy, and shared contract verification
  passed.
- `python scripts/run_memory_tests.py --tb=short` could not start the
  disposable PostgreSQL/TimescaleDB/pgvector and Neo4j tests because the
  Docker executable was unavailable on this host.

See [the safety specification](../../docs/safety-and-privacy.md) for the
full risk register and clinical approval gates.
