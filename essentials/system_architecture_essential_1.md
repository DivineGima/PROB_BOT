# Essentials Phase 1 (MVP) — Football Reliability Screener and Probability Bot

## Aim & Outcome
The product is a personal, $0, probabilities-only Telegram bot: each morning Divine uploads the screener's JSON and receives 1X2 and O/U 0.5–5.5 probabilities from three models (Dixon-Coles, pi-rating, bivariate Poisson) fitted nightly, with every prediction logged and scored so calibration can be measured against the league-frequency baseline (success = beat it on RPS over ≥ 300 logged matches). This single phase is the whole MVP: it covers every PRD_1 build step, in order, as Stages 1–7 below. It ends with a live, monitored system and the go-live checklist signed off.

Source PRD: PRD_1.md

Source Architecture Version: system_architecture_1.md

Revision: Rev-1, amended in place on 2026-10-16 after `/plan-eng-review`, at Divine's explicit instruction. Changed lines are tagged `[Rev-1]`. The version stays 1. Rev-2 (same day): Divine's decisions on A-1 to A-4 (tagged `[Rev-2]`). Rev-3 (2026-10-17): outcomes of the Stage 1 and Stage 2 builds (tagged `[Rev-3]`); scope is unchanged. Rev-4 (2026-10-17): outcomes of the Stage 3 and Stage 4 builds and live runs, plus a code review (tagged [Rev-4]); scope is unchanged. **Rev-5 (2026-10-17): Stages 5 and 7 below are SUPERSEDED by `system_architecture_essential_2.md` (version 2 of the PRD and architecture: nightly pre-computed forecasts, ADR-042) and Stage 6 is re-specified there. Stages 1 to 4 stay complete and unchanged. Only the superseded notes were added; the original text of Stages 5 to 7 is kept for the record and is no longer a build instruction.** The file's own `Source Architecture Version` line stays `system_architecture_1.md` because Stages 1 to 4 were built against it; the read order in `claude.md` therefore continues with essentials 2 for the remaining stages.

## Source Architecture Components
References only, grouped by stage; nothing is duplicated here. All stages also obey `## Extensibility & Change-Tolerance` and `claude.md`.

**Stage 1**
- §7.6 Project structure; §9.3 CI/CD (`ci.yml`, `deploy.yml`); §9.7 Branching discipline
- §5 Data model (Stage 1 creates only `processed_updates`, `uploads`, `events`, `job_runs` in migration `0001`; each later stage creates its own tables, ADR-033 [Rev-1]); §5.7 Invariants
- §6.2 Telegram inbound webhook; §6.5 module interfaces `auth`, `repo` (skeleton only)
- §9.1 Secrets and tokens inventory; §9.8 Legal register (create `docs/legal/source_terms_register.md`, all sources disabled)
- §8.10 / ADR-013 CPU budget and fallback ladder
- ## Extensibility & Change-Tolerance (all five rules apply from the first migration)

**Stage 2**
- §8.5 Ingestion, reconciliation and aliases; §6.8 External APIs (I-6); §6.7 CLI `bootstrap`, `ingest`, `healthcheck`
- §5.2 Reference tables (`competitions`, `teams`, `team_aliases`); §5.3 Results data (`matches`, `source_fetch_log`)
- §9.8 Legal and compliance register; §9.4 error handling and retries; §4.1 GR gaps on team names and rollover
- `data/canonical_teams.json` from PRD_1 §12 (team table), `data/historical_teams.json`, ADR-008, ADR-010, ADR-025, ADR-027, ADR-031, ADR-032 [Rev-1], ADR-035 [Rev-2]

**Stage 3**
- §8.1 Grid engine and markets; §8.2 Dixon-Coles row; §8.7 baseline and scoring definitions
- §5.4 Model registry (`model_runs`, `model_params`); §6.7 CLI `fit`, `backtest` [Rev-4] `fit` was built in Stage 4, where the run tables are created (ADR-033); Stage 3 builds `backtest`.
- §9.5 Testing strategy (property, golden vectors, synthetic leagues); ADR-005, ADR-009, ADR-019
- §3.6 Fit-job compute budget

**Stage 4**
- §8.2 Pi-rating and Bivariate Poisson rows; §8.3 Ensemble weighting; §8.4 Drift inputs (`team_form`); §8.6 Promotion gate and publishing
- §5.4 Model registry (`model_runs`, `active_run`, `model_params`, `team_form`); §6.7 CLI `fit`, `publish`
- §7.9 nightly data-flow; §7.11 model-run state machine; ADR-004, ADR-006, ADR-007, ADR-019, ADR-020, ADR-021, ADR-022, ADR-026, ADR-030 [Rev-1]

**Stage 5**
- §6.1 File contract (Zod v1); §6.2–6.4 Telegram inbound/outbound and behaviour matrix; §6.5 module interfaces; §6.6 error catalogue
- §7.3 Worker components; §7.8 auth flow; §7.10 morning-upload data flow; §7.11 prediction lifecycle
- §8.1 grid engine (TS port), §8.4 drift filter, §8.7 prediction log, §8.8 reply rendering, §8.10 CPU gate
- §5.5 Prediction log; §9.4 error handling; §9.6 idempotency; ADR-005, ADR-012, ADR-013, ADR-021, ADR-024, ADR-026, ADR-029, ADR-034 [Rev-1]

**Stage 6**
- §8.7 Prediction log and scoring; §8.3 Ensemble weighting (rolling RPS); §5.5 Prediction log; `calibration_snapshots`
- §6.7 CLI `score`, `report`; §7.9 nightly flow (score step, Monday report); §7.11 prediction lifecycle
- §9.2 Observability (weekly report); ADR-016, ADR-020, ADR-024, ADR-028 [Rev-1]

**Stage 7**
- §9.2 Observability (events, alerts, watchdog); §9.3 `nightly.yml`; §9.4 error handling; §9.1 S12, S14; §9.7 branching enforcement
- §7.5 Deployment view; §8.10 CPU gate (final re-check); §15 risks R-O1…R-O5, R-P1
- §6.7 CLI `alert`, `healthcheck`; ADR-015, ADR-018, ADR-029 [Rev-1], ADR-036 [Rev-2]

## Build Steps
Work strictly in stage order; a stage's exit criteria must be met (and a `/tracker/` entry written) before the next stage starts. One pull request per step, never to `main` directly.

### Stage 1 — Foundations and the Worker CPU spike (PRD build step 1)
1. **Repo skeleton:** folders per §7.6; `claude.md` present; `.gitignore`, lockfiles, lint/format/typecheck config; `pre-push` hook rejecting `main`; first PR goes through a branch.
2. **Verify-at-build items 1 to 6 (§16) [Rev-1]:** D1 REST batch support and bound-parameter limit; Workers Logs / Time Travel retention; branch-protection and environment availability on a private Free repo. Record results in `docs/legal/` or `docs/verification.md`; if branch protection is unavailable, wire the compensating controls from §9.7. Items 1, 2 and 6 are notes only, written into `docs/legal/source_terms_register.md` (football-data.org free-history depth and terms, co.uk terms, soccernews terms; ADR-032); no source is fetched, A-1 stays Divine's decision, and a negative answer (for example free history is current-season only) is reported to Divine immediately.
3. **D1 migration `0001` [Rev-1, ADR-033]:** only the tables Stage 1 needs, `processed_updates`, `uploads` (with the `received` status), `events`, `job_runs`, with keys, uniques and indexes; every later stage creates its own tables in its own migration; additive-first lint in CI; apply to a local D1 and a real D1.
4. **Repository layers (skeletons):** `apps/bot/src/repo` and `apps/fit/src/footy/repo/d1_client.py` with batching helpers; CI grep check that SQL lives only there.
5. **`auth` module + webhook entry:** path secret, header check (constant time), allowlist `checkSession`, `update_id` dedupe via repo; wrong path/header/user → behaviour matrix of §6.3; Vitest cases S1–S3.
6. **CI workflows:** `ci.yml` (no secrets), `deploy.yml` (merge-of-PR guard, migrations, deploy, `set-webhook`, smoke), gitleaks, no-data-files check. Two Cloudflare tokens created and stored per §9.1.
7. **CPU spike (ADR-013):** deploy a Worker path that runs the real-shaped workload on a 60-match synthetic payload (JSON parse, schema validation placeholder, 3 grids of 169 cells with bivariate-Poisson sums, linear pool, markets, rendering). Measure CPU time over ≥ 20 invocations from production-like runs, reading the `cpuTime` field of the invocation log in Workers Logs (not in-Worker timers, which do not advance during compute) [Rev-1]; record p50/p95/max in `docs/verification.md`.
8. **Decision gate:** if p95 ≤ 6 ms proceed; otherwise apply F1 and re-measure; escalate F2/F3 to Divine as a new architecture version rather than adopting silently. If p95 > 6 ms also hand Divine the parked idea in the tracker (nightly pre-computed grids) [Rev-1]. **[Rev-3] Outcome: p95 22 ms, then 16 ms after F1; gate not met; Divine chose pre-computed grids (architecture ADR-037); the redesign is for PRD_2 and a new architecture version. Stage 1 exit criteria were met and Stage 1 is closed.**
9. **Exit criteria:** CI green on `main`; Worker deployed; webhook rejects bad requests and acks good ones; migrations applied; CPU measurement recorded; `/tracker/` entry written.

### Stage 2 — Ingestion, aliases and bootstrap (PRD build step 2)
1. **Legal gate first:** complete `docs/legal/source_terms_register.md` for football-data.org and football-data.co.uk (verify-at-build items 1, 2, 6; the notes were already gathered in Stage 1, ADR-032 [Rev-1]). A-1 is decided [Rev-2, ADR-035] **and resolved to path 2 on 2026-10-16 [Rev-3]: football-data.org only, co.uk not used, Scottish Premiership dropped; the co.uk loader (`footy load-csv`), the co.uk flag and the two-source join (steps 4 and 5) are not built.** The original rule was: path 1 if the Stage 1 check confirms that downloading football-data.co.uk files by hand for personal use is allowed (Divine downloads them, `footy load-csv` loads them); otherwise path 2: football-data.org only and the Scottish Premiership dropped. The co.uk flag `SOURCE_ENABLED_FDUK` stays off permanently; football-data.org stays off until its entry is signed. Do not fetch anything before this.
2. **Canonical data:** load `competitions` and `teams` from `data/canonical_teams.json`; counts of active clubs must match the PRD table (EPL 20, LL 20, BL 18, SA 20, L1 18, ERE 18, PPL 18, CHA 24, SPL 12, UCL-only 11). [Rev-1] Stage 2 creates its own tables (`competitions`, `teams`, `team_aliases`, `matches`, `source_fetch_log`) in its own migration (ADR-033). Also load the history-only clubs from `data/historical_teams.json` as `active=0` rows with their per-source aliases (ADR-027); a club in neither list is still reported as unmapped, never guessed.
3. **Alias normaliser and resolver:** deterministic normalisation (case, accents, punctuation, "FC/AFC" tokens) with per-source alias files in `data/aliases/`; unmapped names produce an `events` row and a deduped alert — never a guess. Unit tests with hand-written variants.
4. **Source clients:** football-data.org (paced ≥ 6.5 s, token, competition codes of §6.8) and, under A-1 path 1 only, a local football-data.co.uk CSV loader for hand-downloaded files (`footy load-csv --dir <path>`, run on Divine's machine; column-header contract test; no HTTP client for co.uk) [Rev-2]. Both record `source_fetch_log`. Contract tests use hand-written fixtures, not real dumps (ADR-025).
5. **Reconcile:** join rules, ±1 day tolerance, goals preference order, 90-minute basis (`regularTime` / `unverified`), anomaly handling with the "more than 3 disagreements fails the run" rule; forward-only status transitions; idempotent upserts.
6. **`footy bootstrap`:** three seasons across the leagues from the hand-loaded co.uk files (A-1 path 1) or from football-data.org (path 2), plus UCL from football-data.org [Rev-2]; writes only through `apps/fit/src/footy/repo/d1_client.py`, in chunked multi-row bound-parameter statements (at most 100 parameters each), resumable by chunk, never SQL files with literal values (ADR-031) [Rev-1]; row-count and range sanity report.
7. **`footy ingest`:** nightly incremental window (today−7 … today+3); freshness per competition recorded; season-rollover team-list check.
8. **Exit criteria:** `matches` populated and consistent; zero unmapped teams or an explicit documented list; SPL freshness note works (path 1 only); tests green; `/tracker/` entry written.

### Stage 3 — Dixon-Coles, backtest harness and metrics (PRD build step 3 (first half))
1. **Synthetic league generator** (test code): known attack/defence/home advantage/ρ, multiple leagues with a UCL-like link; deterministic seeds.
2. **Scoring module:** RPS (1X2 ordered H/D/A and totals categories 0…12+), log loss, Brier for overs, league-frequency baseline, calibration bins. Hand-computed unit tests.
3. **Grid module (Python reference):** Dixon-Coles τ grid builder, 13×13, renormalisation, markets (1X2, overs 0.5–5.5). Property tests (sum 1, non-negative, monotone overs).
4. **Dixon-Coles fit:** vectorised negative log-likelihood with analytic gradient (scipy), time-decay weights, league offsets and shrinkage, bounds, warm start; sanity checks of §8.2. [Rev-4] Built without a warm start (a cold fit takes about 1 s); iteration cap 3000 and tolerance 1e-10 (the first values, 500 and 1e-12, failed on real data in a few folds). Rates are clipped to 0.01..6 and rho is clamped to its feasible interval when a grid is built (ADR-039).
5. **Parameter recovery test** on synthetic data; convergence-failure path marks the model `failed`.
6. **Walk-forward backtest (`footy backtest`)** over stored matches: per-competition and overall RPS vs baseline; report writer. First real numbers recorded; thresholds and half-life tuned here, labelled as tuning on history, not validation. [Rev-4] Includes a half-life / shrinkage sweep, a paired difference with its standard error and, for several models, the ensemble (weights from earlier folds only). Run in Actions through `data.yml`.
7. **Golden vectors:** emit JSON vectors (inputs → grid cells → markets) into `packages/contracts/golden` for the TypeScript engine in Stage 5; the TypeScript engine is compared cell by cell within 1e-9, with no cross-language hash [Rev-1]. [Rev-4] Files `dc_grid_v1.json`, `pi_grid_v1.json` and `bp_grid_v1.json` (pi and bp were added in Stage 4); they include the clip and clamp cases.
8. **Exit criteria:** Dixon-Coles beats or matches baseline in backtest, or the shortfall is documented and escalated; tests green; `/tracker/` entry written. **[Rev-4] Outcome: met. Production walk-forward over 2,533 matches: Dixon-Coles RPS 0.2044 vs baseline 0.2309, ahead in all nine competitions (`docs/verification.md` section 5).**

### Stage 4 — Pi-rating, bivariate Poisson, ensemble and publishing (PRD build step 3 (second half))
1. **Pi-rating:** transcribe update formulas and constants from Constantinou & Fenton (2013) (verify-at-build item 8), unit-test against hand-computed examples; implement the rating→grid mapping (expected goal difference + league total goals) — a hypothesis to be judged by backtest. [Rev-4] Done: lambda 0.035, gamma 0.7, b 10, c 3, psi(e) = 3 log10(1+e), start at 0 (`docs/verification.md` section 6). The mapping adds one fitted scale s (observed on predicted goal difference, through the origin, clipped to 0.2..2) before the T +/- d split.
2. **Bivariate Poisson:** Karlis–Ntzoufras pmf and fit (shared λ3); property tests; recovery on synthetic data.
3. **Cross-league pooled fit** for all three models with league offsets and shrinkage; per-competition RPS reported (ADR-007). [Rev-4] Dixon-Coles and bivariate Poisson share one pooled structure (league offsets, ridge-shrunk team deviations). The pi-rating is league-agnostic by construction (one scale for all leagues, linked through the Champions League) and has no shrinkage.
4. **Ensemble weights:** softmax of negative rolling RPS with shrinkage to equal weights; initial weights from backtest; weights stored per run and per prediction. [Rev-4] Shrinkage is toward the backtest-derived weights when a `backtest` summary exists, otherwise toward equal weights (the written rule); kappa 100, window 200, pseudo-count 50, all unvalidated starting values (ADR-040). The backtest evaluates the ensemble with weights from earlier folds only. [Rev-4] The backtest prior is used only when its summary was produced with the same half-life and shrinkage as the fit and rests on at least 200 forecasts per model.
5. **`team_form` snapshot:** season and last-10 goals (goals only in v1; the shots columns exist but stay NULL until A-1 is decided, ADR-026), coverage counts, `latest_match_date` [Rev-1]. Stage 4 creates `model_runs`, `active_run`, `model_params`, `team_form` in its own migration (ADR-033). [Rev-4] One row for every active team, including teams with no matches (`n_training = 0`), so the Worker can omit them as INSUFFICIENT_HISTORY and the 95% coverage check can pass (ADR-041).
6. **Run publishing:** payload hashing, promotion gate, atomic `active_run` update, supersede/prune (30 runs), rollback command documented. [Rev-1, ADR-030] The gate is structural checks (at least one model `ok`, `team_form` covers ≥ 95% of active teams, payload hashes verify, row counts plausible) plus a stability guard (no team attack/defence value moves beyond a bound stored in `config_json`, unvalidated); there is no performance comparison in v1. Tests: a corrupted-run fixture and a jumped-parameters fixture are rejected and the old run stays active. [Rev-4] Built as `footy fit` (writes a `building` run; a failed model is stored `failed`) and `footy publish [--run-id ID | --rollback ID]`. Gate: status building, every attempted model has a row and at least one is ok, `team_form` covers 95% of active teams, payload hashes re-verified, payloads cover 95% of teams with training matches, stability bound 0.5. Promotion is one guarded three-statement batch. A rejected run exits with code 4 and writes an `alert` event (a stub; sending is Stage 7). [Rev-4] A run that does not record `n_teams_training` is rejected; the stability guard compares only with verified active payloads; `--run-id ID --accept-drift` skips only the stability guard for one named run and logs `drift_accepted`.
7. **Failure semantics:** per-model `failed` status without silent fallback; all-fail run marked `failed`; alerts hooked to the alert module stub (full alerting in Stage 7).
8. **Backtest comparison:** ensemble vs each model vs baseline; golden vectors for all three grids exported for Stage 5. **[Rev-4] Done (production, 2,861 matches): baseline 0.2304, pi 0.2076, dc 0.2042, bp 0.2042, ensemble 0.2040; all beat the baseline in every competition; dc, bp and the ensemble are statistically tied.**
9. **Exit criteria:** a promoted run readable from D1 through the Worker repo path; gate rejection tested; tests green; `/tracker/` entry written. **[Rev-4] Outcome: met. `RunRepository.readActive` in `apps/bot/src/repo` reads the active run in one batch with a SHA-256 check (Vitest); run `R20261016T232312Z` was promoted in production.**

### Stage 5 — The Telegram bot (upload to reply) (PRD build step 4)

> **[Rev-5] SUPERSEDED.** Build Stage 5a and Stage 5b from `system_architecture_essential_2.md`. Steps 4 (TypeScript grid engine and golden-vector parity), 5 (drift in the Worker) and the model reads of step 3 are not built: the nightly job computes and stores the numbers (ADR-042).
1. **Contract:** Zod schema v1 plus `packages/contracts/screener_v1.schema.json`; valid/invalid fixtures for every `E_SCHEMA_*` branch; business checks (kickoff date = `run_date_utc`, kickoff in (now, now+48h], ≤ 100 matches, size caps). Unknown extra keys are stripped; missing or mistyped required keys are fatal (§6.1) [Rev-1].
2. **Intake:** insert the `uploads` row as `received` first (ADR-029) [Rev-1]; document guard → `getFile` → size-capped download → UTF-8 → JSON → Zod; error replies from the catalogue.
3. **Repo (Worker):** one consistent read of active run, params, `team_form` for involved teams, existing predictions by `fixture_key`; one batched write of upload + predictions + omissions. Stage 5 creates `predictions` and `omissions` in its own migration (ADR-033) [Rev-1].
4. **Engine (TypeScript):** three grid builders and the linear pool; pass all golden vectors within 1e-9; property tests.
5. **Drift and history rules:** `INSUFFICIENT_HISTORY`, drift verdict (goals only in v1, ADR-026) with reasons, omission codes of §4.1 [Rev-1].
6. **Fixture key and immutability:** `INSERT OR IGNORE`; re-upload returns identical stored numbers; the UCL final is treated like any match and the UCL reply note says it may be neutral, with no `NEUTRAL_VENUE` code (ADR-034); `p_*` columns are stored at full precision and a property test shows rounded display values never break the 1e-6 sum CHECK; two identical uploads at once give one set of rows [Rev-1].
7. **Format:** reply blocks, IST/UTC times (an IST time on the next calendar day carries `+1d`), footer (run id, data cut-off, counts by reason, banners, "unvalidated" note, "drift: goals only"), splitting at ≤ 3,900 characters on block boundaries; 429 handling.
8. **Ordering:** persist then reply; failure injection tests (send fails after persist; D1 fails before persist; a simulated killed Worker leaves the upload `received`) [Rev-1].
9. **CPU gate re-check (ADR-013):** measure p95 on production-like uploads of 15, 60 and 100 matches; apply F1 if above 6 ms; escalate otherwise. Also check p95 upload-to-first-reply ≤ 30 s (NFR-11, A-4) in the real-upload check [Rev-2].
10. **Exit criteria:** end-to-end test with fake Telegram green; real upload from Divine answered correctly in the private chat; ignored-chat behaviour verified; `/tracker/` entry written.

### Stage 6 — Scoring, calibration and the weekly report (PRD build step 5)

> **[Rev-5] RE-SPECIFIED** in `system_architecture_essential_2.md` against the version-2 prediction columns. Build from that file.
1. **`footy score`:** match pending predictions to finished matches by `fixture_key` components; void postponed/cancelled/suspended/awarded/unverified; write RPS (1X2, totals) and log loss; idempotent updates (`WHERE status='pending'`). [Rev-1, ADR-028] A pending prediction with no matching finished match 3 days after kickoff becomes void `NO_RESULT` and is listed in one deduped alert.
2. **Rolling per-model RPS** from stored per-model probabilities feeding the weights of §8.3 in the next fit.
3. **Baseline snapshot:** league-frequency forecasts stored per run; paired comparison and bootstrap interval reported as information, not significance claims.
4. **Calibration:** bins for 1X2 outcomes and each over line; `calibration_snapshots` rows; per-competition and per-model breakdowns; omission-rate by reason. `calibration_snapshots` is created in this stage's migration (ADR-033) [Rev-1].
5. **`footy report`:** text summary plus chart (matplotlib) sent to Telegram on Mondays; progress counter toward 300 scored matches; honest wording when the sample is small.
6. **Backtest regression check** wired to `backtest.yml` (monthly + manual) with tolerance.
7. **Tests:** scoring on synthetic fixtures with known answers; idempotent re-scoring; void paths including a rescheduled-match fixture that ends `NO_RESULT` [Rev-1]; report snapshot test.
8. **Whole-nightly-job test [Rev-1]:** one pytest runs `ingest`, `score`, `fit`, `publish` in order on hand-written source fixtures with a SQLite-backed fake D1 client, asserts a promoted run, scored predictions and no unmapped teams, and runs in `ci.yml`.
9. **Exit criteria:** predictions logged in Stage 5 are scored automatically after results arrive; weekly report delivered; whole-job test green; `/tracker/` entry written.

### Stage 7 — Alerts, watchdog, schedule and go-live gates (PRD build step 6)

> **[Rev-5] SUPERSEDED** by Stage 7 of `system_architecture_essential_2.md` (same scope plus the missing-forecast watchdog and the re-measured CPU gate).
1. **Alerts module (Python and Worker):** Telegram sender, `alert_key` dedupe over 24 h, message catalogue for every alert listed in §9.2.
2. **`nightly.yml`:** cron `17 1 * * *` (A-3 accepted [Rev-2]), `workflow_dispatch`, concurrency group, 45-minute timeout, `if: failure()` alert step; first scheduled enablement only after a manual dispatch succeeds end to end.
3. **Watchdog:** Worker scheduled handler every 6 h; alert if `active_run` is missing or older than 36 h, and alert when any `uploads` row is still `received` after 10 minutes (ADR-029) [Rev-1]; STALE MODELS banner in replies verified.
4. **Auto-disable defence:** GitHub's 60-day inactivity auto-disable is documented for public repos only and this repo is private; confirm once (verify-at-build item 5) and document the result; add a keep-alive measure only if the check says it is needed [Rev-1].
5. **Backups and drills:** weekly D1 export artifact; one restore drill; one `active_run` rollback drill; one token-rotation drill (S12).
6. **Final CPU gate:** re-measure on production (ADR-013); record in `docs/verification.md`.
7. **Go-live checklist:** all legal-register entries signed; sources enabled deliberately; CI green; branch controls in place (or compensating controls documented); `claude.md` references `/tracker/`; first 7 consecutive nightly runs green; Divine confirms the first live upload.
8. **Handover:** README runbook (daily ritual, failure table, rotation, rollback; under A-1 path 1, the weekly hand download and `footy load-csv` for the Scottish Premiership) [Rev-2]. Exit criteria: no known silent-failure path; `/tracker/` entry written.

## Added test requirements [Rev-1]
Required proof of behavior the plan already promises, added after the review. Each lands in the stage that owns the code.

| Test | Stage |
|---|---|
| Two identical uploads at once give one set of prediction rows (`INSERT OR IGNORE`) | 5 |
| IST date rollover (`+1d`) for kickoffs after 18:30 UTC | 5 |
| Text message from the allowed chat gets the one-line usage hint | 5 |
| Rounded-probability property test against the 1e-6 sum CHECK | 5 |
| `d1_client` retry/backoff and chunk resume with a fake REST layer | 1 and 2 |
| 6.5 s pacing with a fake clock | 2 |
| Hand-computed ensemble weights and shrinkage | 4 |
| Alert dedupe over 24 h | 7 |
| Stuck-upload watchdog | 7 |
