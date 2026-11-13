# Archit’s phases

Each phase has its own folder in the same repository and workstream branch.

| Phase | Folder | Status |
| --- | --- | --- |
| 05 | [Personalized memory and hybrid retrieval](phase-05-memory/README.md) | Research implementation; verification in docs/phase-05-review.md |
| 06 | [Glucose forecasting](phase-06-forecasting/README.md) | Synthetic research implementation; see model card |
| 07 | [Personalization](phase-07-personalization/README.md) | Reserved; not started |
| 08 | [Safety research](phase-08-safety/README.md) | Reserved; not started |

Phase 05 owns its Python package and unit tests inside its folder. API adapters,
shared contracts, migrations and integration tests stay in their existing shared
locations so the project remains one runnable application. Prasanna’s vision,
nutrition and frontend modules retain their existing locations. The old empty `services/forecasting` and `services/safety` scaffolds were removed;
Archit’s phase implementation belongs here.

Do not copy shared application code into each phase. Future phase packages must
be added to the workspace when implemented; these placeholder folders are not
working forecasting, personalization or safety features.
