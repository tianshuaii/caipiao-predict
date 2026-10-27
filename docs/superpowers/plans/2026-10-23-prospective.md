# Prospective evaluation implementation plan

Execute inline; user authorized implementing the proposed mechanism.

- [x] Add versioned forecast/score/decision storage and additive migration.
- [x] Add leakage guards, scoring, sequential evidence and selection; verify with behavioral tests.
- [x] Integrate prediction workflow, replay and truthful notifications; preserve immutable predictions.
- [x] Expose read-only strategy status and frontend candidate/decision panel; build and test.
- [x] Back up server, migrate, deploy, seed future-only shadows, verify public service.

Existing constraints: five distinct singles per game/issue; historical backtests never count as forward evidence; fail back to uniform; no guarantee of winning improvement.

Verification 2026-10-23: 50 tests pass locally and in server Linux image; frontend TypeScript/Vite build passed. Migration from old schema preserves data. Review findings fixed with failing-then-passing tests: revoked evidence rolls back; evaluate cannot create formal predictions. macOS metadata packaging failure caught by server migration test and fixed through archive filtering and Docker exclusions. Public API and UI asset verified. Production initialization: four frozen candidate forecasts (two per game), zero scores, two decisions, two unchanged official predictions. Repeating evaluation preserved all counts; legacy replay and snapshot hash checks passed. Old image tag before-prospective and DB/source backups retained.
