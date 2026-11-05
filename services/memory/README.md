# Phase 05: Archit's metabolic-memory workstream

Status: initial offline eligibility primitive; Phase 05 is not complete.
The user requested starting the assigned phases on 2026-11-05. This additive
slice leaves shared APIs, schemas, migrations, dependencies and CI unchanged.

`src/t1d_memory/eligibility.py` checks an explicitly supplied canonical episode
snapshot before similarity ranking. It excludes foreign scope, target anchors,
unreviewed/withdrawn episodes, future responses/derivations, late source knowledge,
stale revisions and unusable sources. All constituent confirmations, annotations
and response/context events must be represented in immutable source lineage.
It chooses no response-window duration or ranking weights.

This is an internal research building block, not an authorization boundary or
public request schema. A future adapter must authenticate and apply current
consent/grants/RLS, reconstruct revisions at cutoff using Phase 02, construct
complete lineage, recheck canonically after search and record protected audits.
Boolean flags are trusted adapter assertions, never client-controlled proofs.
No API, persistent episode, graph, embedding, ranking or model is implemented.

## Independent development and handoff

- Prasanna owns vision/nutrition/UI (03/04/09); Archit owns memory/forecasting/
  personalization/safety research (05/06/07/08); integration/evaluation are shared.
- Reuse `MealInput`, `NutritionInput`, `HistoryRecord` and `HistoryPage` in
  `apps/api/src/t1d_api/data/schemas.py`. Do not create competing meal contracts.
- Existing confirmed meals require human-reviewed components, portions, nutrition
  references and exact aggregate agreement. Synthetic confirmed meals can support
  development while Phase 04 is in progress.
- Joint review is still needed for the episode window/completeness definition,
  retrieval response contract, adapters, ranking profile and additive persistence.
- The current GitHub baseline lacks the later local Phase 03 training/notebook
  files described by its review. Prasanna's local changes have not been inspected.

## Verification

No new dependencies. From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'services/memory/src'
python -m unittest discover -s services/memory/tests -v
```

Use the project's Python 3.12 environment. These synthetic tests establish only
the named primitive's behavior. They do not verify database authorization,
retrieval relevance, full-phase acceptance or clinical validity. Integration into
the shared pytest/workspace/CI configuration requires coordinated review.
