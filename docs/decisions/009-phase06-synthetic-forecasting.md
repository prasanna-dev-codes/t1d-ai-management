# ADR 009: baseline-led synthetic forecasting qualification

Date: 2026-11-07. User authorized Phase 06; research-only implementation.

Keep canonical Phase 02 events and current authorization authoritative. Add a
bounded scoped forecast adapter that resolves revisions before time/quality
filtering and retains invalid observations for explicit abstention. Recheck
canonical inputs, current source approval, principal expiry and grants after
inference. Persist an audit reference, not a second health-record database.

Compare persistence, OLS trend and fixed-penalty ridge before adopting deep models.
Use a small six-dimensional standard-library fit and portable finite JSON weights;
no new third-party ML runtime, unsafe pickle, model download or request-controlled
artifact path. Pin the release artifact hash and feature/research policy versions.

Train/calibrate/test on disjoint fictional patients and chronological label windows.
Calibrate per-patient maximum residuals and disclose nominal versus measured
coverage. Keep persistence as explicit default; never auto-promote a candidate
based on the held-out test result. Reject nonsynthetic source types until a new
reviewed real-data artifact, policy and evaluation exist. The source registry is
trusted administrative governance, not permission to relabel actual data.

These technical research input conditions do not approve clinical treatment
thresholds, dosing, production use or Phase 07 adaptation. XGBoost/sequence and
retrieval-enabled comparisons remain deferred pending suitable permitted data.
