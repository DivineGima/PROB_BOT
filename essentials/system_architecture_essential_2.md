# Essentials Phase 2 — Nightly forecasts, the Telegram bot, scoring and go-live — Football Reliability Screener and Probability Bot

## Aim & Outcome
Version 2 changes where the probabilities are computed: the nightly Python job computes and stores one forecast per scheduled fixture, and the Worker only validates the upload, looks the forecasts up, logs the first prediction per fixture and renders the reply (ADR-042). This file holds only the new or changed work. It supersedes **Stages 5 and 7** of `system_architecture_essential_1.md` and re-specifies **Stage 6** against the new prediction columns; Stages 1 to 4 stay as built and complete. Stage 5 is split into **5a** (the Python forecasts) and **5b** (the Worker), because 5b depends on the table 5a creates.

Success is unchanged (PRD_2): beat the league-frequency baseline on RPS over at least 300 logged matches. The Worker must also pass the CPU gate on the lighter workload (p95 at most 6 ms).

Source PRD: PRD_2.md

Source Architecture Version: system_architecture_2.md

Revision: first issue, 2026-10-17, written at Divine's instruction ("create the version files and follow the suggested solution"). Numbered 2, not 3, because `claude.md` requires PRD, architecture and essentials to share N with no gaps.

## Source Architecture Components
References only. All stages also obey `## Extensibility & Change-Tolerance` and `claude.md`.

**Stage 5a (new)**
- §8.11 Nightly forecasts; §8.4 drift (Python); §8.1 grid engine; §8.3 ensemble weights; §5.4 `fixture_forecasts`
- §8.6 promotion gate (forecast check) and pruning; §7.4 fit components; §7.9 nightly flow; §6.7 `footy fit`, `footy publish`
- ADR-042, ADR-044, ADR-033

**Stage 5b (replaces essentials 1 Stage 5)**
- §6.1 file contract (Zod v1); §6.2 to §6.4 Telegram inbound, behaviour matrix, outbound; §6.5 module interfaces; §6.6 error catalogue
- §7.3 Worker components; §7.8 auth flow; §7.10 upload data flow; §7.11 prediction lifecycle
- §8.7 prediction log; §8.8 reply rendering; §8.10 CPU gate; §5.5 `predictions`, `omissions`; §9.4 error handling; §9.6 idempotency
- ADR-005, ADR-012, ADR-013, ADR-021, ADR-024, ADR-026, ADR-029, ADR-034, ADR-043, ADR-045

**Stage 6 (re-specified)**
- §8.7 prediction log and scoring; §8.3 rolling weights; §5.5; `calibration_snapshots` (§5.6)
- §6.7 `footy score`, `footy report`, `footy backtest`; §7.9 nightly flow; §9.2 observability; §9.3 `backtest.yml`
- ADR-016, ADR-020, ADR-024, ADR-028, ADR-046

**Stage 7 (replaces essentials 1 Stage 7)**
- Unchanged from essentials 1 Stage 7 except the items marked [v2] below.

## Build Steps
Work strictly in stage order; a stage's exit criteria must be met (and a `/tracker/` entry written) before the next stage starts. One pull request per step, never to `main` directly.

### Stage 5a — Nightly forecasts (Python)
1. **Drift module (`footy/drift.py`):** pure functions `assess_team` and `assess_fixture` implementing §8.4: fewer than 10 training matches, fewer than 10 in the last-10 window, no `team_form` row or no current-season mean → `INSUFFICIENT_HISTORY`; otherwise goals drift above the threshold (tolerance 1e-9) → `DRIFT`; `INSUFFICIENT_HISTORY` wins over `DRIFT`. Hand-computed tests for each branch and for a difference of exactly the threshold.
2. **Migration `0004_fixture_forecasts.sql`:** the table of §5.4 with its CHECKs and index. Additive. The Python migration test and the Worker table-list test are updated for the new table.
3. **Forecast builder (`footy/forecast`):** a pure `build_forecast` per fixture and a `ForecastRepo` (the only SQL) that reads scheduled fixtures in the window and writes rows with `INSERT OR IGNORE` in resumable chunks. Property tests: probabilities sum to 1, overs monotone, markets of the pooled grid equal the weighted sum of the models' markets; a model that cannot build a grid is left out and named; no model → `NO_MODEL`; weights renormalised over the models present.
4. **`footy fit` writes the forecasts:** after the models, weights and `team_form`, build forecasts for the window (today to today + 4 UTC), record `n_forecast_fixtures` and the verdict counts in `diagnostics_json`, write the rows after the run row. `config_json` gains the forecast settings. A database failure while writing leaves the run `building` and the job failed (the gate then rejects it).
5. **Gate and pruning:** `evaluate_gate` rejects a run that did not record `n_forecast_fixtures` or has fewer forecast rows than recorded (zero fixtures passes). `footy publish` prunes forecasts outside the newest 5 servable runs (`active`, `superseded`, `building`; rejected and failed runs take no slot; never the active run's) and `delete_runs` deletes a run's forecasts first. The gate also requires the new run to forecast at least half of the fixtures the active run forecast for the new run's start date or later (carry-over; skipped by `--accept-drift`). A rollback to a run with no forecasts succeeds with a warning in the summary.
6. **Tests:** end-to-end fit → forecasts → publish on a synthetic world with scheduled fixtures; a corrupted/partial forecast set is rejected and the old run stays active; rollback moves forecasts and parameters together; pruning keeps the active run's forecasts; mutations (drift sign, weights not renormalised, gate skipping the forecast check) each fail a test.
7. **Exit criteria:** `footy fit` on the synthetic world produces forecasts that publish; gate rejection tested; tests green; `/tracker/` entry written. A live `fit` and `publish` on production (Divine) produces forecast rows in D1 (checked in the Stage 5b real-upload step).

### Stage 5b — The Telegram bot (upload to reply)
1. **Migration `0005_predictions.sql`:** `predictions` and `omissions` per §5.5 (full-precision `p_*`, `total_json`, `match_date`, `baseline_json`, CHECK sums and monotonicity, `run_id` without a foreign key, `UNIQUE(fixture_key)`, `UNIQUE(upload_id, label)`). Additive.
2. **Contract:** Zod schema v1 (`intake/schema.ts`); `packages/contracts/screener_v1.schema.json` generated from it by `z.toJSONSchema` and checked in CI for drift; valid and invalid fixtures for every `E_SCHEMA_*` branch. Unknown keys are stripped; missing or mistyped required keys are fatal; `home` must differ from `away`; duplicate `match_id` labels become `DUPLICATE_PAIR`.
3. **Intake (`intake/`):** document guard (`.json` name or JSON MIME), size pre-check from `document.file_size`, strict UTF-8 (a BOM is tolerated), JSON parse, `schema_version` check before Zod, at most five validation paths in the error text, no file content echoed.
4. **Telegram client (`telegram/`):** `getFile`, size-capped streamed download, `sendMessage` with `retry_after` handling for 429 up to 5 s and one retry for other failures; plain `fetch` injected for tests; the token never appears in logs, errors or events (ADR-043). Only this module reads `TELEGRAM_BOT_TOKEN` (the repo check is extended).
5. **Repo (`repo/`):** `ForecastRepository.readActiveForDate`, `PredictionRepository.insertManyIgnoreDuplicates` (one `INSERT ... SELECT ... FROM json_each(?1) ... ON CONFLICT (fixture_key) DO NOTHING` statement, bound parameters only: only a fixture-key clash is ignored, a CHECK failure raises) and `findByDate`, `OmissionRepository.insertMany`, `TeamRepository.resolveCanonical`, one batched write of predictions, omissions and the upload finalisation, then a read-back. `RunRepository.readActive*` are marked deprecated.
6. **Upload pipeline (`upload/`):** inserts the `uploads` row as `received` before any download (ADR-029); a fixture already in the log is shown from the log first (also after kickoff); for a new fixture the business checks run in the order `DATE_MISMATCH`, `STARTED`, `TOO_FAR`, `UNMAPPED_TEAM`, `DUPLICATE_PAIR`, then the forecast lookup (`NO_FORECAST` or the stored `INSUFFICIENT_HISTORY` / `DRIFT` / `NO_MODEL` verdict) [as built, architecture 19.1]; creates predictions by copying the forecast; first prediction immutable; re-upload returns the stored numbers marked "already logged"; the UCL final is treated like any match and the UCL note says it may be neutral (ADR-034).
7. **Reply (`format/`):** blocks as in §8.8 with IST and the `+1d` rule, footer (run id, data cut-off, counts by reason, screener exclusions by `G1`–`G6`/`OTHER`, banners STALE MODELS, model unavailable, no forecasts stored, UCL note, "drift: goals only", "unvalidated"), splitting at 3,900 characters on block boundaries; team names come from our table; free text from the file is never echoed.
8. **Entry and ordering:** the webhook acknowledges first; the document pipeline runs in `ctx.waitUntil`; any other message from the allowed chat gets the one-line usage hint; persist then reply; unexpected errors reply `E_INTERNAL` with an id and write an event; no active run replies `E_NO_RUN` with an event.
9. **Tests (Vitest, local D1, fake Telegram `fetch`):** every behaviour-matrix row of §6.3; two identical uploads at once give one set of rows; IST `+1d` for kickoffs after 18:30 UTC; usage hint; rounded display values never break the 1e-6 sum CHECK (property test); failure injection (send fails after persist, D1 fails before persist, a simulated killed Worker leaves the upload `received`); replay of the same `update_id`; ignored chats; injection strings in every free-text field; 100-match upload; subrequest count.
10. **CPU gate re-check (ADR-013):** measure p95 on production-like uploads of 15, 60 and 100 matches from Workers Logs `cpuTime`; also check p95 upload-to-first-reply ≤ 30 s (NFR-11). If above 6 ms apply F1 and then escalate. **Needs Divine's account actions (deploy, `TELEGRAM_BOT_TOKEN` secret, a real upload); recorded in `docs/verification.md` when done.**
11. **Exit criteria:** end-to-end test with fake Telegram green; real upload from Divine answered correctly in the private chat; ignored-chat behaviour verified; CPU gate recorded; `/tracker/` entry written. The last three need production and are tracked as in-progress until Divine runs them.

### Stage 6 — Scoring, calibration and the weekly report
1. **`footy score`:** settle pending predictions as in §8.7 (scored; void with reason; an unverified finished result waits 3 days like a missing result before it is voided `UNVERIFIED_RESULT`; `NO_RESULT` after 3 days), idempotent, one deduped alert listing the `NO_RESULT` void predictions.
2. **Rolling per-model RPS:** recompute each model's 1X2 RPS from `models_json` and the result for the most recent scored predictions in which every fitted model forecast the match; `footy fit` passes the aligned history to `ensemble_weights`. Falls back to the backtest prior and then equal weights while there are none.
3. **Baseline and interval:** the baseline comes from each prediction's `baseline_json`; the report gives the paired difference and a percentile bootstrap interval (fixed seed), worded as information.
4. **Calibration:** bins for the three 1X2 outcomes and each over line; per-competition and per-model breakdowns; omission rate by reason (omitted and published both counted per processed upload); `calibration_snapshots` row per report. Migration `0006_calibration_snapshots.sql`.
5. **`footy report [--send] [--monday-only]`:** text summary plus a matplotlib chart (reliability curve and RPS bars) sent to Telegram with `sendMessage` and `sendPhoto`; progress toward 300 scored matches; honest wording for small samples; no snapshot when nothing is scored.
6. **Backtest regression check:** `backtest.yml` (monthly and manual) runs `footy backtest --models dc,pi,bp --fail-on-regression`; the result is compared with the previous comparable stored backtest and a rise of more than 0.003 RPS exits 4 and writes an alert event.
7. **Tests:** settle on synthetic fixtures with known answers (RPS, log loss); idempotent re-scoring; every void path including a rescheduled match that ends `NO_RESULT`; aligned-history rule with a model that skips fixtures; weights from rolling RPS change with the data; bootstrap interval deterministic and brackets a known difference; calibration bins; report text snapshot for small and large samples; chart bytes are a PNG; Telegram sender with a fake session (success, 429, failure); regression check passes and fails correctly.
8. **Whole-nightly-job test:** one pytest runs `ingest`, `score`, `fit`, `publish` in order on hand-written source fixtures with a SQLite-backed fake D1, with a prediction logged between nights, and asserts a promoted run with forecasts, a scored prediction and no unmapped teams; it runs in `ci.yml`.
9. **Exit criteria:** predictions logged in Stage 5b are scored automatically after results arrive; the weekly report is delivered; whole-job test green; `/tracker/` entry written. Delivery of a real report and the first scored predictions need production and time; tracked as in-progress until they happen.

### Stage 7 — Alerts, watchdog, schedule and go-live gates
As in essentials 1 Stage 7, with these [v2] additions: the watchdog also alerts when the active run has no forecast rows for today or tomorrow while `matches` holds scheduled fixtures for those days; the final CPU gate re-measures the Stage 5b workload; the README runbook explains `NO_FORECAST` and how to rebuild forecasts (run `fit` and `publish`). The Telegram sender built in Stage 6 (`footy/telegram.py`) is reused by the alerts module.

## Added test requirements
| Test | Stage |
|---|---|
| Drift boundary: difference exactly equal to the threshold passes | 5a |
| Forecast markets equal the weighted sum of the models' markets | 5a |
| Gate rejects a run with missing forecast rows; old run stays active | 5a |
| Pruned forecasts never include the active run's | 5a |
| Two identical uploads at once give one set of prediction rows | 5b |
| A stored prediction never changes when a newer forecast differs | 5b |
| Each `NO_FORECAST` / verdict omission appears with its reason | 5b |
| Reply shows names from our table, never free text from the file | 5b |
| `NO_RESULT` void for a rescheduled match | 6 |
| Aligned RPS history when a model skips a fixture | 6 |
| Alert dedupe over 24 h | 7 |
| Stuck-upload watchdog; missing-forecast watchdog | 7 |
