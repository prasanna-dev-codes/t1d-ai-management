# ADR 010 — Chronological offline forecast adaptation

Status — implemented first research slice, 2026-11-11.

Phase 07 needs a measurable comparison between a new participant's frozen
Phase 06 forecast and a forecast that can learn from that participant's
earlier errors. The Phase 06 point artifacts are reused through their
checksum-validated prediction path. The offline harness scores the same
points before changing them and verifies the original Phase 06 held-out MAE.

Feedback is participant-scoped and matures at the later of the last target
time and the latest recorded availability across horizons. Unknown actual
logging times in the public research data use the same declared event-time
replay assumption as Phase 06. Ohio official testing files are held out from
feedback. The unsplit sources allow earlier, matured test-stream outcomes
to update later forecasts in the explicitly chronological warm track.

The first seven days supply the fixed correction and the cold-start
comparison. The rolling method uses the previous 14 days of outcomes.
An optional context correction uses the reported meal and exercise flags
and the observed CGM trend. Regularization, a minimum sample count, and a
bound on correction size limit the effect of small or unusual samples.
These are statistical parameters for offline evaluation.

Method selection and calibration use different participants from the Phase 06
calibration pool. All reported test cohorts have been used in earlier
retrospective evaluations. Fresh independent validation and richer verified
context remain necessary before using any personalized artifact in the app.
Future physiology-informed research needs provenance and reviewed definitions
for its inputs. The first implementation evaluates observed glucose outcomes
and produces aggregate forecast metrics.

The follow-up meal-memory comparison uses the existing Phase 05 relative
carbohydrate distance on available meal records. It routes a different
forecast only when earlier eligible meals are retrieved. The personal
interval comparison holds point forecasts fixed and reuses matured forecast
errors to estimate each participant's recent variability. Independent
calibration participants fit the normalized interval. See
[the evaluation](../../phases/phase-07-personalization/MEMORY_AND_INTERVALS.md).

The offline profile now exports calibration and binds it to the Phase 06
model checksums and horizon recipe. A forecast query can run without its
future glucose labels. The
[independent T1D-UOM evaluation](../../phases/phase-07-personalization/INDEPENDENT_VALIDATION.md)
holds the selected point and interval profiles fixed. Phase 05 service
responses are exercised with confirmed synthetic meals and fixture-backed
storage.
