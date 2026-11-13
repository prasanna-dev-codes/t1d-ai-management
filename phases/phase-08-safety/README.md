# Safety Engine & Clinical Research Simulation

Owner: Archit. Workstream: `workstream/archit-phases-05-08`.

The Phase 08 research safety implementation reuses the existing Phase 06
synthetic input policy and adds a final forecast output gate. The local
workflow exercises confirmed meal revisions, Phase 05 evidence, Phase 06
forecasts, Phase 07 adaptation, and audit handling. The positive workflow
test crosses the production HTTP routes with fixture-backed stores.

The [regression report](REGRESSION_REPORT.md) maps the tests to the roadmap
and records the clinical simulation deferral. The
[design decision](../../docs/decisions/011-phase08-research-safety.md) records
the safety boundary.

## Run locally

From the repository root in PowerShell, using the existing workspace
environment:

```powershell
$env:PYTHONPATH = (Resolve-Path 'phases/phase-07-personalization').Path
.venv\Scripts\python.exe phases/phase-08-safety/research_demo.py --scenario all
.venv\Scripts\python.exe phases/phase-08-safety/research_demo.py --comparison
.venv\Scripts\python.exe -m pytest -q phases/phase-08-safety/tests
```

The demo emits one JSON record per scenario. Eligible output has four
glucose forecasts and intervals. The comparison emits aggregate errors for
the three methods on the same eight fictional cutoffs. Shifted intervals
in the personalized demo are illustrative and carry a review-required label.
