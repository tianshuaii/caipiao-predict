# Four-Game Unified Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 七乐彩 and 七星彩 to the complete audited workflow while upgrading all four games to one rule-driven analysis, research, combination, and prospective-evaluation architecture.

**Architecture:** Preserve existing draw/prediction JSON and frozen strategy versions for ssq/dlt. Add a registry that describes unordered zones, special numbers, and ordered digit positions, then route validation, parsing, feature construction, selection, settlement, workflow, APIs, and UI through it. New algorithms generate new version fingerprints and must pass rolling research evaluation; only frozen prospective evidence may change formal recommendations.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, NumPy/SciPy/scikit-learn, React/TypeScript, pnpm/Vite, MySQL 8.4.

**Spec:** `docs/superpowers/specs/2026-11-02-four-game-unified-analysis-design.md`

## Global Constraints

- Preserve all existing ssq/dlt draw, prediction, settlement, candidate-score, strategy-decision, and artifact records byte-for-byte.
- A new selection/model/feature implementation must create a new version identity and starts prospective evidence at zero.
- Use official public sources as primary; preserve every fetched response and reject source conflicts, repeated pages, malformed results, and incomplete historical inventories.
- Unknown prize values are `null`/pending, never zero.
- Formal strategy promotion remains: at least 60 valid frozen samples, ≥1% cumulative Brier improvement, latest-30 superiority, and version-specific e-value threshold.
- Default formal output remains 5 unique single tickets, 10 simulated yuan per game/issue; no purchase, multiplier, banker, or compound-ticket features.
- Statistical and model UI copy must state that historical structure and backtests do not prove future advantage.

## Review Focus

- QXC may repeat the same digit across positions; ticket validation and generation must allow this while retaining position order.
- QLC special numbers must remain separate from the seven basic numbers in feature, probability, selection, and award matching paths.
- The 2020-10-11 QXC rule boundary must prevent cross-version model training and use the correct historical award function.
- Source disagreement or incomplete prize data must block prediction/scoring rather than be silently accepted.
- Legacy ssq/dlt replay must produce the same tickets and settlement summaries after the generic registry ships.

---

### Task 1: Verify and fixture official QLC/QXC sources

**Files:**
- Create: `backend/tests/fixtures/qlc_primary_page.json`
- Create: `backend/tests/fixtures/qlc_secondary_page.html`
- Create: `backend/tests/fixtures/qxc_primary_page.json`
- Create: `backend/tests/fixtures/qxc_secondary_page.html`
- Create: `docs/reports/2026-11-02-qlc-qxc-source-verification.md`
- Modify: `backend/lottery/collectors.py`
- Test: `backend/tests/test_collectors.py`

**Interfaces:**
- Consumes: persisted `RawFetch`, existing `fetch()` and `normalize()` behavior.
- Produces: verified field mappings and parser fixtures for `parse_qlc_primary`, `parse_qlc_secondary`, `parse_qxc_primary`, and `parse_qxc_secondary`.

- [ ] **Step 1: Capture bounded read-only samples from each primary and secondary source, record URL/parameters/date/field map in the report, and add sanitized responses as fixtures.**
- [ ] **Step 2: Write failing parser tests for a normal result, an official prize field missing amount/count, malformed number text, and a primary/secondary number disagreement.**
- [ ] **Step 3: Run `backend/.venv/bin/python -m pytest backend/tests/test_collectors.py -q` and verify the new parser tests fail because the parsers do not exist.**
- [ ] **Step 4: Implement the four pure parser functions in `backend/lottery/collectors.py`; preserve every official field required by the spec and leave missing award values as `None`.**
- [ ] **Step 5: Re-run the collector tests and verify they pass.**
- [ ] **Step 6: Commit with `git add backend/lottery/collectors.py backend/tests/test_collectors.py backend/tests/fixtures docs/reports && git commit -m "test: verify qlc and qxc source formats"`.**

### Task 2: Introduce the versioned game and zone registry

**Files:**
- Create: `backend/lottery/game_specs.py`
- Modify: `backend/lottery/domain.py`
- Modify: `backend/lottery/ingestion.py`
- Test: `backend/tests/test_game_specs.py`
- Test: `backend/tests/test_domain.py`
- Test: `backend/tests/test_ingestion.py`

**Interfaces:**
- Consumes: canonical issue strings and existing ssq/dlt `front`/`back` records.
- Produces: `GameSpec`, `ZoneSpec`, `game_spec(game, issue)`, `validate_draw(game, issue, zones)`, `validate_ticket_data(game, issue, zones)`, and compatibility helpers returning legacy `front`/`back` where applicable.

- [ ] **Step 1: Write failing tests that define ssq/dlt compatibility, qlc 7 basic values plus one distinct special value, qxc ordered positions with repeated digits allowed, and rejection of an invalid qxc seventh value.**
- [ ] **Step 2: Run the focused game-spec tests and verify the failures are due to missing registry APIs.**
- [ ] **Step 3: Implement immutable specifications for ssq, dlt, qlc, qxc-new, and qxc-pre-2020-10-11; make rule-version selection explicit by issue/date boundary.**
- [ ] **Step 4: Adapt domain validation and ingestion comparison to use normalized zone payloads without modifying stored legacy draw JSON.**
- [ ] **Step 5: Run `backend/.venv/bin/python -m pytest backend/tests/test_game_specs.py backend/tests/test_domain.py backend/tests/test_ingestion.py -q`; verify legacy and new-game cases pass.**
- [ ] **Step 6: Commit with `git add backend/lottery/game_specs.py backend/lottery/domain.py backend/lottery/ingestion.py backend/tests && git commit -m "feat: add versioned four-game rule registry"`.**

### Task 3: Implement QLC/QXC historical collection, inventory, and migration

**Files:**
- Create: `backend/migrations/versions/009_four_game_zones.py`
- Modify: `backend/lottery/collectors.py`
- Modify: `backend/lottery/ingestion.py`
- Modify: `backend/lottery/calendar.py`
- Modify: `config/calendar.json`
- Test: `backend/tests/test_collectors.py`
- Test: `backend/tests/test_data_history.py`
- Test: `backend/tests/test_workflow.py`

**Interfaces:**
- Consumes: parser functions from Task 1 and registry from Task 2.
- Produces: `collect(session, 'qlc'|'qxc', full)`, verifiable inventory records, and safe next-target calculation for four games.

- [ ] **Step 1: Write failing tests for paginated full import, duplicate-page refusal, inventory completeness, calendar closure skip, and no new prediction when the target-year calendar has not been reviewed.**
- [ ] **Step 2: Run the focused tests and verify the new games are rejected by the old game whitelist.**
- [ ] **Step 3: Add the additive migration for normalized-zone metadata/indexes only; do not update prior rows.**
- [ ] **Step 4: Add source collection and independent cross-check ingestion for QLC/QXC; use per-game parser selection, preserve raw fetches, and implement current official schedules and cutoffs.**
- [ ] **Step 5: Extend annual calendar validation to require entries for all registered games, and add only reviewed official closure ranges.**
- [ ] **Step 6: Run `backend/.venv/bin/python -m pytest backend/tests/test_collectors.py backend/tests/test_data_history.py backend/tests/test_workflow.py -q` and verify all pass.**
- [ ] **Step 7: Commit with `git add backend/migrations backend/lottery config/calendar.json backend/tests && git commit -m "feat: collect qlc and qxc with audited inventory"`.**

### Task 4: Generalize ticket selection, settlement, and frozen replay

**Files:**
- Modify: `backend/lottery/selection.py`
- Modify: `backend/lottery/settlement.py`
- Modify: `backend/lottery/workflow.py`
- Modify: `backend/lottery/portfolio.py`
- Test: `backend/tests/test_selection.py`
- Test: `backend/tests/test_settlement_service.py`
- Test: `backend/tests/test_workflow.py`
- Test: `backend/tests/test_portfolio.py`

**Interfaces:**
- Consumes: `GameSpec` plus probability payload keyed by zone/position.
- Produces: `select_tickets(game, seed, count, protocol, probabilities)`, `settle_ticket(game, ticket, draw)`, and frozen payloads that replay with their saved protocol.

- [ ] **Step 1: Write failing tests for deterministic qlc/qxc batches, qlc special number matching, all qlc award levels, qxc position matching, and repeated qxc digits in one ticket.**
- [ ] **Step 2: Add regression tests that replay representative existing ssq/dlt prediction fixtures unchanged.**
- [ ] **Step 3: Run the selection/settlement tests and verify the qlc/qxc cases fail before implementation.**
- [ ] **Step 4: Implement structure-aware uniform and weighted selection, 5-ticket de-duplication, coverage/similarity measures, and rule-versioned settlement. Keep legacy selector code reachable for stored legacy protocol identities.**
- [ ] **Step 5: Run `backend/.venv/bin/python -m pytest backend/tests/test_selection.py backend/tests/test_settlement_service.py backend/tests/test_workflow.py backend/tests/test_portfolio.py -q`.**
- [ ] **Step 6: Commit with `git add backend/lottery backend/tests && git commit -m "feat: settle and replay all four game structures"`.**

### Task 5: Build registry-driven statistics and advanced feature analysis

**Files:**
- Modify: `backend/lottery/feature_service.py`
- Modify: `backend/lottery/indicators.py`
- Modify: `backend/lottery/data_history.py`
- Modify: `backend/lottery/api.py`
- Test: `backend/tests/test_feature_service.py`
- Test: `backend/tests/test_indicators.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: retained historical draw snapshots and `GameSpec` zone descriptors.
- Produces: `analyze_features(rows, game, zone, cutoff_issue, window)` for unordered/special zones and `analyze_position_features(rows, game, position, cutoff_issue, window)` for qxc.

- [ ] **Step 1: Write failing tests for qlc basic/special separation, all requested windows, qxc per-position frequencies/omissions/012 routes/transitions, and `null` for metrics that do not apply.**
- [ ] **Step 2: Write failing tests that prove conflict or unavailable as-of records produce HTTP 409 rather than calculated features.**
- [ ] **Step 3: Run the focused tests and verify the new API contract is unavailable.**
- [ ] **Step 4: Implement frequency, omission, hot/cold, composition, co-occurrence, entropy, transition, distribution, and anomaly feature groups with window/data-hash/version metadata.**
- [ ] **Step 5: Extend the feature catalog/API contract with game-aware zones and positions while retaining existing front/back responses.**
- [ ] **Step 6: Run `backend/.venv/bin/python -m pytest backend/tests/test_feature_service.py backend/tests/test_indicators.py backend/tests/test_api.py -q`.**
- [ ] **Step 7: Commit with `git add backend/lottery backend/tests && git commit -m "feat: add unified game statistics and position features"`.**

### Task 6: Add reproducible model recipes and rolling research evaluation

**Files:**
- Modify: `backend/lottery/model_training.py`
- Modify: `backend/lottery/experiments.py`
- Modify: `backend/lottery/jobs.py`
- Modify: `backend/lottery/experiment_registry.py`
- Modify: `backend/lottery/generation_versions.py`
- Test: `backend/tests/test_model_training.py`
- Test: `backend/tests/test_experiments.py`
- Test: `backend/tests/test_registry.py`

**Interfaces:**
- Consumes: zone/position feature matrices and fixed research protocol configuration.
- Produces: zone-aware model probability outputs, version fingerprints, and rolling evaluation records for `uniform`, `frequency`, `bayesian`, `logistic`, `forest`, and `boost` recipes.

- [ ] **Step 1: Write failing tests for independently normalized QLC basic/special probabilities, independently normalized QXC position probabilities, rule-boundary exclusion, deterministic model artifacts, and time-ordered rolling splits.**
- [ ] **Step 2: Write failing tests that unsupported XGBoost/LightGBM/LSTM/Transformer configurations are rejected until their locked dependency and resource recipe is registered.**
- [ ] **Step 3: Run the model and registry tests and verify missing recipe/shape support causes the expected failures.**
- [ ] **Step 4: Implement the production research recipes, including a documented Bayesian-smoothed baseline; version every recipe by its code/config/dependency fingerprint.**
- [ ] **Step 5: Make rolling research output Brier, calibration, hit/award outcomes, cost, return, ROI, drawdown, and matched frozen-random comparison, all marked exploratory.**
- [ ] **Step 6: Run `backend/.venv/bin/python -m pytest backend/tests/test_model_training.py backend/tests/test_experiments.py backend/tests/test_registry.py -q`.**
- [ ] **Step 7: Commit with `git add backend/lottery backend/tests && git commit -m "feat: add four-game reproducible research recipes"`.**

### Task 7: Extend frozen prospective scoring and promotion to four structures

**Files:**
- Modify: `backend/lottery/prospective.py`
- Modify: `backend/lottery/ranking.py`
- Modify: `backend/lottery/evaluation.py`
- Modify: `backend/lottery/performance.py`
- Test: `backend/tests/test_prospective.py`
- Test: `backend/tests/test_ranking.py`
- Test: `backend/tests/test_evaluation.py`
- Test: `backend/tests/test_performance.py`

**Interfaces:**
- Consumes: frozen candidate probability/ticket payloads from Task 6.
- Produces: comparable structure-aware Brier scores, candidate status, rankings, and the existing promotion decision contract.

- [ ] **Step 1: Write failing tests for qlc Brier vectors that keep special separate and qxc position one-hot Brier vectors; include a failed or late forecast exclusion case.**
- [ ] **Step 2: Write regression tests that prove ssq/dlt candidate metrics and e-value threshold allocation remain unchanged for legacy records.**
- [ ] **Step 3: Run the prospective/evaluation tests and verify they fail at unsupported game encoding.**
- [ ] **Step 4: Implement generic scoring encoders and portfolio aggregation while retaining 60 samples, 1% improvement, recent-30, e-process, fallback, and ranking semantics.**
- [ ] **Step 5: Run `backend/.venv/bin/python -m pytest backend/tests/test_prospective.py backend/tests/test_ranking.py backend/tests/test_evaluation.py backend/tests/test_performance.py -q`.**
- [ ] **Step 6: Commit with `git add backend/lottery backend/tests && git commit -m "feat: score four-game prospective candidates"`.**

### Task 8: Generalize API contracts and frontend types

**Files:**
- Modify: `backend/lottery/api.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/strategies.ts`
- Modify: `frontend/src/components/Balls.tsx`
- Modify: `frontend/src/components/DrawTable.tsx`
- Test: `backend/tests/test_api.py`
- Test: `frontend/tests/api.test.ts`
- Test: `frontend/tests/strategies.test.ts`

**Interfaces:**
- Consumes: four-game views and feature/result payloads.
- Produces: discriminated TypeScript ticket/draw types and APIs that report game metadata, zones/positions, and preserved legacy shapes.

- [ ] **Step 1: Write failing backend/API and TypeScript tests for qlc/qxc game selectors, zone-aware draw views, qxc ordered ticket serialization, and legacy ssq/dlt response compatibility.**
- [ ] **Step 2: Run the focused API/frontend tests and confirm the type/game unions reject `qlc` and `qxc`.**
- [ ] **Step 3: Implement discriminated payloads plus compatibility adapters; ensure user-supplied unsupported game/zone/position values return 422.**
- [ ] **Step 4: Update shared ball and draw rendering to display unordered basic/special balls and ordered numbered positions without changing legacy rendering.**
- [ ] **Step 5: Run `backend/.venv/bin/python -m pytest backend/tests/test_api.py -q` and `cd frontend && pnpm test -- api.test.ts strategies.test.ts`.**
- [ ] **Step 6: Commit with `git add backend/lottery/api.py frontend/src backend/tests frontend/tests && git commit -m "feat: expose four-game typed API views"`.**

### Task 9: Upgrade the analysis, strategy, review, and research UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AnalysisPanel.tsx`
- Modify: `frontend/src/components/StrategyPanel.tsx`
- Modify: `frontend/src/components/RankingPanel.tsx`
- Modify: `frontend/src/components/ResearchPanel.tsx`
- Modify: `frontend/src/components/CombinationPanel.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/app.test.tsx`
- Test: `frontend/tests/analysis.test.tsx`

**Interfaces:**
- Consumes: Task 8 contracts, feature catalog, research results, prospective status, and coverage/similarity metrics.
- Produces: four-game selector and zone/position-aware visualizations with correct uncertainty copy.

- [ ] **Step 1: Write failing UI tests for selecting each of four games, QLC special-number labelling, QXC seven-position display, non-applicable metric treatment, and the mandatory research/prospective boundary copy.**
- [ ] **Step 2: Run the focused component tests and verify they fail because only two games are rendered.**
- [ ] **Step 3: Render registry metadata through the overview, draw archive, analysis, review, strategy, ranking, and combination pages; add coverage/similarity presentation to combination output.**
- [ ] **Step 4: Make model labels distinguish production research recipes from disabled experimental recipes; do not offer a production action for LSTM/Transformer.**
- [ ] **Step 5: Run `cd frontend && pnpm test -- app.test.tsx analysis.test.tsx` and `pnpm build`.**
- [ ] **Step 6: Commit with `git add frontend/src frontend/tests && git commit -m "feat: add unified four-game research UI"`.**

### Task 10: Schedule, migrate, verify, and document production readiness

**Files:**
- Modify: `backend/lottery/scheduler.py`
- Modify: `backend/lottery/reporting.py`
- Modify: `backend/lottery/monitoring.py`
- Modify: `README.md`
- Modify: `deploy/README.md`
- Create: `docs/reports/2026-11-02-four-game-acceptance.md`
- Test: `backend/tests/test_scheduler.py`
- Test: `backend/tests/test_monitoring.py`
- Test: `backend/tests/test_reporting.py`

**Interfaces:**
- Consumes: all registered game specs, verified inventories, reviewed calendars, and prospective status.
- Produces: all-game nightly execution, safe morning reporting, clear monitoring state, and release evidence.

- [ ] **Step 1: Write failing tests that a nightly run processes each due game, skips undrawn/closed games, fails closed for missing year calendars/inventory conflicts, and never queues a notification during analysis.**
- [ ] **Step 2: Write failing tests for an all-four-game morning report that reads frozen valid predictions only.**
- [ ] **Step 3: Run the scheduler/monitoring/reporting tests and confirm the old two-game loop fails the new assertions.**
- [ ] **Step 4: Implement registry-driven scheduling, reporting and monitoring; document source, rule, calendar, migration, rollback and validation operations.**
- [ ] **Step 5: Run `backend/.venv/bin/python -m pytest backend/tests -q`, `cd frontend && pnpm test`, and `pnpm build`; record exact commands/results in the acceptance report.**
- [ ] **Step 6: Run an isolated migration rehearsal against a copied database, verify no legacy row changes, and capture record-count/fingerprint/replay checks in the acceptance report.**
- [ ] **Step 7: Commit with `git add backend README.md deploy docs && git commit -m "feat: prepare four-game production workflow"`.**

## Self-review

- **Spec coverage:** Tasks 1--3 cover trusted data, rules, calendars, and migrations; 4 covers selection/settlement; 5 covers the statistics/advanced-feature layers; 6 covers research models and rolling backtests; 7 covers formal evidence; 8--9 cover APIs/UI; 10 covers operations and acceptance.
- **Step scan:** Every implementation task begins with a failing behavior test and ends with focused verification and a commit.
- **Type consistency:** `GameSpec` is the single producer for zone shape; all later tasks consume it rather than adding new game conditionals.
- **Review Focus:** Each listed risk is explicitly assigned tests in Tasks 2, 3, 4, 6, and 7.
- **Proportion:** This is a multi-subsystem programme. Tasks are grouped by independently reviewable deliverables while preserving dependency order.
