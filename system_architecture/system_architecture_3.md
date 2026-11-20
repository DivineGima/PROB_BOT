# System Architecture — Football Reliability Screener and Probability Bot

Derived From: PRD_3.md

| Field | Detail |
|---|---|
| Architecture version | 3 (full snapshot of version 2 plus the version-3 changes: read-only bot commands; changelog below, §6.10, §8.12 and §20). Version 2 was a full snapshot of version 1 with Rev-1 to Rev-4 folded in, plus the version-2 changes (§8.11, §19) |
| Date | 2026-11-21 (version 2: 2026-10-17; version 1: 2026-10-15) |
| Author | Divine Gima Folabit (owner) with Claude (System Designer) |
| Status | **Locked for build** on Divine's delegated authority ("I leave you the liberty to ask, to answer, and close the gaps"). Four amendment candidates (§4.3) are flagged for Divine; none blocks Stage 1 of Essentials 1. [v3] Version 3 was written by Claude Code at Divine's instruction on 2026-11-21; the command list, the verdicts-only rule for `/fixtures` and the exclusion of state-changing commands are Divine's decisions of that day. |
| Revision | **Version 3, 2026-11-21.** A new numbered snapshot of version 2. Passages that changed in version 3 are tagged `[v3]`; the `[v2]` and `[Rev-1]` to `[Rev-4]` tags are kept. The full list of version-3 changes is the changelog below and §20. **Version 2, 2026-10-17.** A new numbered snapshot, not an in-place amendment. Passages that changed in version 2 are tagged `[v2]`; the older `[Rev-1]` to `[Rev-4]` tags are kept so the history stays readable. The full list of version-2 changes is the changelog below and §19. |
| Source of truth order | `PRD_3.md` → this file → `/essentials/*` → code |

---

## Changelog

### Version 3 (2026-11-21): read-only bot commands

Derived from `PRD_3.md` (decisions 30 to 34). Lifts the v1 exclusion "bot commands beyond the upload flow" (§1.4, ADR-016) for read-only commands only.

| Ref | Change | Where |
|---|---|---|
| ADR-049 | The Worker answers ten read-only commands from the allowlisted chat through a new `commands/` module: `/help` (`/start`), `/status`, `/fixtures`, `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team`, `/alerts`. They read stored rows through a new read-only `QueryRepository` and render plain text. They write nothing except the existing `processed_updates` row and, on an unexpected failure, one `command_failed` event | §1.4, §2.1, §5.7, §6.2, §6.3, §6.5, §6.10, §7.3, §7.12, §8.12 |
| ADR-050 | `/fixtures` shows the stored verdict per fixture and never a probability; probabilities are shown only for an uploaded file's fixtures, and again by `/logged` and `/results` for predictions already logged | §6.10, §8.12 |
| ADR-051 | No command changes state: no re-run, rollback, publish or void from chat; no GitHub or Cloudflare token enters the Worker | §1.4, §13, §14 |
| ADR-052 | One command list, `packages/contracts/bot_commands.json`, read by the Worker's registry and by `scripts/set-webhook.mjs`, which registers Telegram's menu with `setMyCommands` scoped to the allowlisted chat; a failed menu registration is a deploy warning, not a failure | §6.4, §6.10, §9.3 |
| Usage hint | Gains a second line, "Send /help to see the commands." (additive) | §6.3 |
| Threats | S15 command arguments, S16 operational data in replies, S17 menu disclosure | §9.1 |
| Invariant 9 | The command path writes no prediction, omission, upload, forecast, run, form or snapshot row | §5.7 |

**Unchanged:** the upload flow (§6.1, §7.10, §8.7, §8.8), the data model (no migration), the models and the nightly job, the Python CLI, authentication (the same three layers in the same `auth` module), the secrets (no new one), the workflows except one input of the `set-webhook` step, cost ($0).

**Downstream Impact on Essentials:** IMPACT. `system_architecture_essential_3.md` adds Stage 8 (bot commands). Stages 1 to 7 of essentials 1 and 2 are unchanged and stay as built.

### Version 2 (2026-10-17): nightly pre-computed forecasts

Derived from `PRD_2.md`. Resolves ADR-037, which version 1 recorded as a direction without a design.

| Ref | Change | Where |
|---|---|---|
| ADR-042 | The nightly job computes and stores one forecast row per scheduled fixture in the next days (ensemble and per-model 1X2 and total-goals distribution, the history/drift verdict, the league baseline). The Worker looks the row up. The TypeScript grid, drift and ensemble code is not built. | §1.1, §1.2, §5.4, §7, §8.1, §8.4, §8.10, §8.11 |
| ADR-043 | The Worker calls the Telegram Bot API with plain `fetch`; grammY is not used (trim step F1). No new Worker dependency. | §6.5, §7.3, §9.1 |
| ADR-044 | History and drift verdicts are computed in Python at forecast time (`footy/drift.py`), one implementation. | §8.4 |
| ADR-045 | `predictions` rows are self-contained (forecast values, weights, drift and baseline copied in) and `predictions.run_id` is a plain column, not a foreign key, so old runs can be pruned. | §5.5 |
| ADR-046 | Rolling per-model RPS from logged predictions feeds the next fit; weekly report, calibration snapshots and a backtest regression check (informational) are specified. | §6.7, §8.3, §8.7, §9.3 |
| ADR-047 | The Worker validates the screener file with a hand-written validator; the Zod schema stays the contract source and a differential test keeps the two equal. | §6.1, §6.5, §8.10 |
| ADR-048 | The Worker CPU target (p95 6 ms) is missed after the F1 trim and accepted by Divine; the Stage 7 watchdog is the safety net. | §8.10, R-P1 |
| New omission code | `NO_FORECAST`: the fixture has no stored forecast. The Worker never computes a number itself. | §5.5, §6.3 |
| New table | `fixture_forecasts` (migration 0004). `predictions` and `omissions` (0005) and `calibration_snapshots` (0006) keep their ADR-033 stage ownership. | §5 |
| Gate | The promotion gate also requires the run's forecast rows to be present (§8.6). | §8.6 |

**Unchanged:** the models, the grid and market definitions (§8.1 minus the TypeScript parity), the 10-match rule, the drift thresholds, the screener file contract (§6.1), authentication, the data sources and the legal register, the migration discipline, cost ($0).

**Downstream Impact on Essentials:** IMPACT. `system_architecture_essential_1.md` Stages 5 and 7 are superseded by `system_architecture_essential_2.md` (Stage 5 is split into 5a, the Python forecasts, and 5b, the Worker, and builds no TypeScript model code; Stage 7 gains a watchdog check for missing forecasts). Stage 6 keeps its scope and is re-specified in essentials 2 against the new prediction columns. Stages 1 to 4 are unchanged and stay complete.

---

## 0. How to read this file

| If you want… | Go to |
|---|---|
| What is being built and what is not | §1 |
| Requirements with IDs | §2 |
| Back-of-the-envelope numbers and free-tier budgets | §3 |
| Every PRD gap I closed, and what I need you to confirm | §4 |
| Database structure | §5 |
| API / interface structure (Telegram, file contract, internal modules, CLI) | §6 |
| Project structure, frontend/backend flow, auth flow, data flow, C4 diagrams | §7 |
| Deep dives (grid engine, models, ensemble, drift, ingestion, publishing, log) | §8 |
| Security, performance, observability, CI/CD, errors, idempotency, branching, legal | §9 |
| The locked Extensibility & Change-Tolerance rules | `## Extensibility & Change-Tolerance` |
| Coding methodology and fullstack constraints | §11, §12 |
| Review/simplification record | §13 |
| ADRs (cumulative) | §14 |
| Risks and mitigations | §15 |
| What was verified vs. what must be verified at build | §16 |
| The engineering-review amendments (Rev-1) | §18 |
| The version-2 design (nightly forecasts) | Changelog, §8.11, §19 |
| The version-3 design (bot commands) | Changelog, §6.10, §8.12, §20 |

Terminology: **bot** = the Cloudflare Worker. **fit job** = the Python GitHub Actions job. **screener** = the Claude Project (outside this repo, manual). **run** = one immutable set of fitted model parameters (`model_runs` row). **fixture key** = the bot's own identity for a match (§8.7).

---

## 1. Problem framing and scope (design phase 1)

### 1.1 What the system is
A single-user, $0, probabilities-only analytics tool. Each morning Divine sends "run today" to the screener (a Claude Project), which applies reliability gates G1–G6 to the day's fixtures and emits a schema-v1 `.json` file. Divine uploads it to a Telegram bot. The bot validates it, looks up the forecast that the nightly job stored for each match (probabilities, history rule and drift verdict already computed from the models fitted overnight) [v2], and replies with P(1X2) and P(over) at 0.5–5.5. Every prediction is logged and later scored so calibration can be measured. [v3] From the same chat Divine can also send read-only commands that show what is stored (§6.10).

### 1.2 The core design insight
The system has two very different workloads, and the architecture follows that split (ADR-001):

| Workload | Shape | Where it runs | Why there |
|---|---|---|---|
| Fit models, ingest data, compute per-fixture forecasts, score results |  Heavy, batch, once a night, minutes of CPU, needs numpy/scipy | Python on GitHub Actions | Workers cannot do this inside 10 ms CPU [v2: nor the grid arithmetic itself, measured in Stage 1] |
| Serve a morning upload | Tiny, real-time, milliseconds: validate the file, look up stored forecasts, log, render [v2] | TypeScript Cloudflare Worker | Free, always on, sits next to D1 |

This matches the batch-training / online-inference split in the project's ML-system-design resource (RESOURCE 3): heavy training offline, light serving online, a registry of model versions, and a monitoring loop that feeds labels back.

### 1.3 In scope (v1)
Everything in PRD_1 §6 (six core features): screener contract, drift filter, probability engine, ensemble with pre-batch re-evaluation, Telegram bot, prediction log with calibration. [v3] Plus the read-only bot commands of PRD_3 decision 30 (§6.10).

### 1.4 Out of scope (v1) — explicit
BTTS, correct score, corners, cards, xG, odds, Europa League screening, Claude plain-language reading, any web UI (optional Pages dashboard is v2), bot commands that change state (re-run, rollback, publish, void; [v3] read-only commands are in scope, ADR-049, ADR-051), probabilities outside an uploaded file [v3, ADR-050], inline keyboards and callback queries [v3], multi-user support, closing-odds benchmarking, shadow predictions for omitted matches, staging environment.

### 1.5 System boundary
Inside: bot Worker, D1, fit job, CI/CD, the repo. Outside (trusted only through contracts): Telegram, football-data.org, football-data.co.uk, the screener (Claude Project and the web pages it reads), Divine.

---

## 2. Requirements (design phase 2)

IDs are used by tests and essentials to trace work back to the PRD.

### 2.1 Functional

| ID | Requirement | PRD ref |
|---|---|---|
| FR-01 | Accept a `.json` document from the allowed chat only; ignore every other chat silently | §7 Functional, §8 Security |
| FR-02 | Download via Telegram Bot API and validate against schema v1 before any computation | §7 Functional |
| FR-03 | Per accepted match return P(home), P(draw), P(away) and P(over) for 0.5, 1.5, 2.5, 3.5, 4.5, 5.5; Under = 1 − Over | §7 Functional |
| FR-04 | Derive all markets from one scoreline grid per match | §6 feature 3 |
| FR-05 | Drift-check each team (last 10 matches vs season average, goals only in v1; the shots check is deferred, ADR-026 [Rev-1]); omit failing matches and say why. [v2] The check is evaluated in the nightly forecast step and shown by the bot | §6 feature 2 |
| FR-06 | Three models (Dixon-Coles, pi-rating, bivariate Poisson) refit and re-scored before each daily batch, combined as an ensemble | §6 feature 4 |
| FR-07 | Ensemble weights from rolling RPS; if a model fails to fit, run the others and flag it | §5 Ensemble weighting, §10 |
| FR-08 | Log every prediction with inputs and model version; add result when the match finishes | §7 Functional |
| FR-09 | Void postponed/cancelled matches; score only 90 minutes plus stoppage time | §10 |
| FR-10 | Omit matches with a team under 10 matches of training data, with reason | §10 |
| FR-11 | Split long replies into several Telegram messages | §10 |
| FR-12 | Reject non-JSON / malformed / wrong-version files with an error reply and compute nothing | §10 |
| FR-13 | On upload download failure reply with an error and ask to resend | §10 |
| FR-14 | Nightly job at 01:17 UTC (06:47 IST) [Rev-2, A-3]: ingest finished results, refit, re-score, write parameters [v2] and per-fixture forecasts to D1; send Telegram alert on failure | §8 Deployment |
| FR-15 | Report RPS, log loss and calibration curves; walk-forward backtest as a regression check | §6 feature 6 |
| FR-16 | Team names map to the canonical list; bot keeps an alias table per source spelling | §7 Data |
| FR-17 | Source rate limit/outage: use cached data (D1), retry next run, alert | §10 |
| FR-18 | [Rev-1] An upload that is acknowledged but never answered raises an alert within about 6 hours (ADR-029) | §10 (review D7) |
| FR-19 | [Rev-1] A pending prediction whose match never shows as finished is voided `NO_RESULT` 3 days after kickoff and listed in an alert (ADR-028) | §10 (review D8) |
| FR-20 | [v2] The nightly job stores a forecast (probabilities, history rule, drift verdict) for every scheduled fixture in the next days; the bot only looks forecasts up and never computes a probability (ADR-042) | PRD_2 decision 27 |
| FR-21 | [v2] A match with no stored forecast is omitted with `NO_FORECAST` and listed in the reply | PRD_2 decision 28 |
| FR-22 | [v2] Ensemble weights use the rolling RPS of logged predictions as soon as they exist; a weekly report with calibration is sent on Mondays | PRD_2 build step 5 |
| FR-23 | [v3] Answer the read-only commands of §6.10 from the allowed chat only; every other chat is ignored as in FR-01 | PRD_3 decision 30 |
| FR-24 | [v3] Commands only read stored rows: no command computes a probability, logs or changes a prediction, starts a job or changes a run (ADR-049, ADR-051) | PRD_3 decisions 32, 33 |
| FR-25 | [v3] `/fixtures` shows the stored verdict per fixture and never a probability (ADR-050) | PRD_3 decision 31 |
| FR-26 | [v3] An unknown command gets a one-line pointer to `/help`; any other text gets the usage hint, which gains a `/help` line | PRD_3 §10 |
| FR-27 | [v3] Command dates are UTC calendar dates; replies longer than one message are split as in FR-11 | PRD_3 decision 34 |

### 2.2 Non-functional

| ID | Requirement | Measured by |
|---|---|---|
| NFR-01 | Cost $0: Workers Free, D1 Free, GitHub Free (private repo), no paid add-ons | Budget table §3.5 |
| NFR-02 | Bot CPU per upload ≤ 10 ms (Workers Free limit); design target p95 ≤ 6 ms for a 60-match payload. [v2] The Worker does no model arithmetic, so this is judged on parsing, validation, D1 and rendering | CPU gate (ADR-013, Essentials 2, Stages 5b and 7) |
| NFR-03 | Subrequests per invocation ≤ 50; design target ≤ 35 | Subrequest budget §3.4 |
| NFR-04 | Correctness: every grid sums to 1 (±1e-9); 1X2 and O/U derived from the same grid; Under = 1 − Over exactly | pytest + Vitest property tests |
| NFR-05 | Secrets never in code or logs; Cloudflare token used by the nightly job is D1-scoped | Secret scan in CI, §9.1 |
| NFR-06 | Idempotent: re-sending the same update or file never creates duplicate predictions | Unique keys, §9.6 |
| NFR-07 | Calibration quality judged by RPS, log loss, calibration curves; success = beat league-frequency baseline on RPS over ≥ 300 logged matches | §8.9 |
| NFR-08 | Silent failure is a defect: a missed or stale nightly run must be detected and alerted | Watchdog, ADR-015 |
| NFR-09 | Private repo; no raw source data committed; tests use synthetic data | CI check, ADR-025 |
| NFR-10 | Every change via feature branch and pull request; never push to `main` | Branch protection, §9.7 |
| NFR-11 | [Rev-2, A-4] Reply latency: p95 ≤ 30 s from upload to the first reply message | Timing in the Stage 5 end-to-end test and the real-upload check |
| NFR-12 | [v3] Command reply p95 ≤ 10 s from message to the first reply; CPU per command below an upload's (target p95 ≤ 6 ms, Free limit 10 ms) | Workers Logs `cpuTime` and timing in the Stage 8 check |

---

## 3. Scale and budget math (design phase 3)

### 3.1 Traffic (one user)

| Quantity | Estimate | Basis |
|---|---|---|
| Uploads per day | 1–3 | One "run today" per morning, occasional re-upload |
| Fixtures per day across 10 competitions | typically 15–45; very full weekend ≈ 80–85 | Weekend maxima: EPL 10, LL 10, BL 9, SA 10, L1 9, ERE 9, PPL 9, CHA 12, SPL 6 (per round, spread over 2–3 days) |
| Matches surviving gates | 20–40% of fixtures → typically 5–15, hard cap 100 per file | Gate strictness is unvalidated |
| Webhook requests per day | < 50 (including ignored chats) | Workers Free allows 100,000/day |
| Nightly job runs | 1 per day, plus manual dispatches | |
| Commands per day [v3] | 5–30 | One user checking status and fixtures; far below 100,000 requests/day |

### 3.2 Payload sizes

| Item | Size | Note |
|---|---|---|
| One match object in the JSON | ≈ 0.5–1.0 KB (with absences and URLs) | |
| Daily file | typically < 15 KB; worst case 100 matches ≈ 100 KB | Hard cap **256 KB** checked before and after download (Telegram allows up to 20 MB, so the cap is ours) |
| Reply text per match | 250–800 characters (PRD estimate) | |
| Reply messages per upload | 15 matches × 600 chars ≈ 9 KB → 3 messages; worst case 100 × 800 = 80 KB → 21 messages | Telegram text limit 4,096 characters; we chunk at ≤ 3,900 |

### 3.3 Storage (D1 Free: 500 MB per database, 5 GB per account)

| Table group | Rows (3-year window) | Approx. size |
|---|---|---|
| `matches` | ≈ 10,000 historical + ≈ 3,200 per season going forward | ≈ 3–5 MB |
| `team_aliases`, `teams`, `competitions` | ≈ 900 aliases, 179 current clubs plus ≈ 60 history-only clubs [Rev-1], 10 competitions | < 0.2 MB |
| `model_params` | 3 blobs per run × ≈ 30–60 KB; keep last 30 runs | ≈ 3–6 MB (≈ 55 MB/yr if never pruned) |
| `team_form` | ≈ 179 rows per run × 30 runs [Rev-1] | < 1 MB |
| `fixture_forecasts` [v2] | ≈ 200–400 rows per run (5-day window) × ≈ 2 KB, kept for the newest 5 servable runs | ≈ 4 MB at most |
| `predictions` | ≈ 10/day × ≈ 3 KB (forecast values, per-model markets, drift, inputs; no grid [v2]) | ≈ 11 MB/yr |
| `events`, `job_runs`, `uploads`, `processed_updates` | small; `events` pruned at 90 days | < 5 MB/yr |
| **Total, year 1** | | **< 40 MB (≈ 8% of the 500 MB cap)** |

Retention rule: pruning old `model_params` rows is *data lifecycle*, not schema removal; predictions copy everything they need from the forecast, so they stay reproducible after the params and the forecasts are pruned [v2].

### 3.4 Per-invocation budgets for the Worker (Free plan)

| Budget | Limit (verified, §16) | Planned use for a 15-match upload | Worst case (100 matches) |
|---|---|---|---|
| CPU time | 10 ms | [v2] parse + validate + render only; to be measured in the Stage 5b CPU gate | same, 100 matches (risk R-P1) |
| Subrequests (fetch + D1 calls + Telegram calls) | 50 | getFile 1 + download 1 + D1 batches ≈ 6 + sendMessage 3 = **11** | 2 + 6 + 21 = **29** |
| D1 queries per invocation | 50 | ≈ 6 batched calls | ≈ 6 |
| Memory | 128 MB | < 10 MB | < 20 MB |

Rule: the repository layer exposes **batched** reads/writes; no per-match query loops.

[v3] A command uses at most 2 D1 batch calls and at most 5 `sendMessage` calls (at most 7 subrequests), with no `getFile`, no download and no file validation (§6.10).

### 3.5 Free-tier budget summary

| Resource | Limit | Planned use | Headroom |
|---|---|---|---|
| Workers requests/day | 100,000 | < 50 | > 99.9% |
| D1 rows read/day | 5,000,000 | nightly fit reads ≈ 15,000 rows; bot ≈ 500 | > 99% |
| D1 rows written/day | 100,000 | nightly ≈ 300 (+ ≈ 15 predictions) ; bootstrap once ≈ 15,000 | > 99% |
| GitHub Actions minutes/month (private, Free) | 2,000 | nightly ≈ 12 min × 30 = 360; CI ≈ 5 min × 40 PRs = 200; monthly backtest ≈ 60 | ≈ 70% headroom |
| football-data.org | 10 requests/minute | ≈ 10–12 requests/night, paced at ≥ 6.5 s apart | within limit |
| Telegram | ≈ 1 message/second per chat | ≤ 21 messages, sequential | within limit |

### 3.6 Fit-job compute

≈ 9,300 domestic matches (3 seasons × nine leagues) plus UCL from go-live; 179 active clubs (≈ 240 in the full training window including history-only clubs) [Rev-1]. Dixon-Coles with vectorised negative log-likelihood and analytic gradients: seconds to a few minutes. Pi-rating: one chronological pass. Bivariate Poisson: similar to Dixon-Coles. Target total nightly wall-clock ≤ 15 minutes; hard timeout 45 minutes.

---

## 4. PRD gap resolutions and amendment candidates

`PRD_1.md` is saved as supplied (plus the two mechanical edits noted at its top). Where it is silent, ambiguous or technically infeasible, this file closes the gap. Divine delegated that authority; every closure is listed so nothing is silent. "Closed" means the architecture now defines the behaviour. "Amend" means the PRD itself should change in a future `PRD_2.md` — Divine states the version number when he pastes it; nothing here edits PRD_1.

### 4.1 Gaps closed in this architecture

| # | PRD gap or issue | Closure | Where |
|---|---|---|---|
| GR-01 | Canonical team table was empty in the pasted PRD | Filled from the earlier draft Divine supplied; stored in PRD_1 appendix and seeded into `teams` | PRD_1 §12, §5 |
| GR-02 | PRD refers to "section 3/7/9/11" but headings were unnumbered | Headings numbered 1–12 in PRD_1 so references resolve | PRD_1 |
| GR-03 | PRD says "acknowledge immediately and compute in the background because of the CPU limit" — this rationale is wrong: `ctx.waitUntil` does not lift the 10 ms CPU limit | Keep fast acknowledgement (it avoids Telegram retries and slow-webhook errors) but the CPU risk is handled separately: measured CPU gate plus a fallback ladder | ADR-013, §8.10 |
| GR-04 | PRD says football-data.org supplies nine competitions and football-data.co.uk only SPL; but "last 3 seasons" of history cannot be assumed from the free football-data.org tier (third-party sources say current season only; not confirmed officially) | football-data.co.uk CSVs supply **history and shots for all nine domestic leagues**; football-data.org supplies fresh fixtures/results and UCL. Live use of each source is gated by the legal register | ADR-008, §9.8; amendment A-1 (decided, Rev-2: ADR-035) |
| GR-05 | UCL has no free history source | UCL results accumulate from go-live. If football-data.org free tier returns earlier UCL seasons, bootstrap uses them (verify at build). UCL-only clubs with < 10 matches are omitted by FR-10 | ADR-008, §8.5 |
| GR-06 | "Elo **or** pi-rating" | Pi-rating (matches the stack row and Constantinou & Fenton) | ADR-006 |
| GR-07 | Pi-rating gives expected goal difference, not a scoreline grid | Map to λ_home, λ_away via expected goal difference and a league total-goals level, then independent-Poisson grid; labelled hypothesis, decided by backtest | ADR-006 |
| GR-08 | Models trained on pooled data across leagues, but leagues connect only through UCL | Pooled fit with league offsets and shrinkage of team parameters toward their league mean; labelled hypothesis; UCL predictions flagged as lower-confidence | ADR-007 |
| GR-09 | "Last 3 seasons" — does the current partial season count? | Rolling window of 1,095 days ending at the data cut-off, exponential time decay inside it | ADR-009 |
| GR-10 | `match_id` format `YYYY-MM-DD_COMP_HOME_AWAY` contains spaces, accents and `/` | Bot treats it as an opaque display label; identity is `fixture_key` derived from date, competition and resolved team ids | ADR-012 |
| GR-11 | Where are calibration reports delivered (bot accepts only uploads)? | Weekly Telegram message (and chart image) pushed by the fit job; `calibration_snapshots` table keeps history. No bot commands in v1. [v3] Superseded in part: read-only commands exist, including `/report` as text (ADR-049); the weekly push and its chart stay | ADR-016 |
| GR-12 | PRD alerts only on job *failure*; a job that never starts (GitHub schedule skipped/disabled) is silent | Worker cron-trigger watchdog checks the active run's age; stale-run banner on every reply when age > 36 h | ADR-015 |
| GR-13 | Re-uploading the same fixture later (maybe with different inputs) would bias calibration | First prediction per fixture is immutable and is the one scored; re-uploads are answered from the log and flagged "already logged" | ADR-012 |
| GR-14 | Drift check is described but not defined numerically | Defined in §8.4 with starting thresholds (goals ±0.6 per match; shots ±25%), snapshotted per run and labelled **unvalidated**. **[Rev-1] v1 ships goals-only; the shots check is deferred until A-1 is decided** | ADR-021, ADR-026 |
| GR-15 | Ensemble weight formula undefined | Softmax of negative rolling RPS with shrinkage to equal weights while few scored matches exist | ADR-020 |
| GR-16 | A prediction logged after kickoff would be leakage | Matches whose kickoff is not strictly in the future (or > 48 h away) are omitted with reason | §8.7, §6.2 |
| GR-17 | SPL results come only from football-data.co.uk, which updates about twice a week → SPL form/results can lag 3–4 days | Per-competition freshness is recorded; SPL replies carry a "data through <date>" note; SPL predictions scored late. Risk R-M5. [Rev-2] With hand-loaded files, SPL freshness is the date of the last file Divine loaded; load weekly | §8.5 |
| GR-18 | Shots exist only for domestic leagues via co.uk and lag goals | Shots used only when ≥ 8 of the last 10 matches have shots; otherwise goals-only and the reply says so. **[Rev-1] Deferred: v1 is goals-only, shots columns stay NULL** | §8.4, ADR-026 |
| GR-19 | Bot behaviour for non-document messages from the allowed chat | One-line usage reply; no commands. [v3] Commands added (§6.10); any other text still gets the hint, with a second line pointing to `/help` | §6.3 |
| GR-20 | Season rollover (promotion/relegation/UCL draw) is "update each summer" with no process | `data/canonical_teams.json` + alias seeds changed by pull request; alias test enforces completeness; nightly coverage check compares football-data.org competition team lists with `teams` | §8.5 |
| GR-21 | Extra-time handling needs a data rule | Use football-data.org `score.regularTime` when `score.duration` is not `REGULAR`; if absent, mark result `unverified`, exclude from training/scoring, alert | ADR-010 |
| GR-22 | UCL final is played at a neutral venue; no neutral flag in the file | Home advantage is applied anyway (one match per year); documented limitation R-M6. **[Rev-1] Decided: treated like any match; the UCL reply note says the final may be neutral; no `NEUTRAL_VENUE` omission** | §15, ADR-034 |
| GR-23 | [Rev-1] `teams` was seeded only from the 2026-27 list, but the 1,095-day window includes clubs that have since left the ten competitions; their matches would be dropped as unmapped and the league links through moved clubs lost | `data/historical_teams.json` seeds history-only clubs as `active=0` with per-source aliases; Stage 2 counts = 179 active + the listed history-only clubs; clubs in neither list are still reported, never guessed | §5.2, §8.5, ADR-027 |
| GR-24 | [Rev-1] A rescheduled match changes its kickoff date, so its `fixture_key` can never match a finished match and the prediction would stay `pending` forever | `footy score` voids `pending` predictions with no matching finished match 3 days after kickoff (`void_reason='NO_RESULT'`) and lists them in one deduped alert | §8.7, ADR-028 |
| GR-25 | [Rev-1] If the Worker is killed at the CPU limit after acknowledging, there is no reply and no event row (a silent failure, NFR-08) | `uploads` row written as `received` before heavy work; the watchdog alerts if one is still `received` after 10 minutes | §6.2, §9.2, ADR-029 |
| GR-26 | [Rev-1] The promotion gate compared a 14-day walk-forward score that is in-sample for the new run and was never defined | v1 gate = structural checks plus a parameter stability guard; no performance comparison | §8.6, ADR-030 |
| GR-27 | [Rev-1] Bulk bootstrap by SQL files with literal values contradicted "bound parameters only" (S10) | Bootstrap writes through the Python repo layer in chunked, resumable bound-parameter statements | §6.8, ADR-031 |

### 4.2 Observations for the screener (Claude Project prompt) — not architecture, but you should know

1. **G5 "first-team player" is undefined** and the injuries source can contain stale or duplicate rows, so gate G5 will be noisy. The bot only stores absences; it does not use them in v1.
2. `excluded[]` entries carry `HOME vs AWAY` text with no `match_id`; the bot only counts them by reason.
3. The prompt does not require `kickoff_utc` to fall on `run_date_utc`; the bot enforces it (omission `DATE_MISMATCH`).
4. The prompt text says "also send the end result … as a .Json file". Output must be a **file**, not a code block, and `Content` must be pure JSON with no surrounding text — otherwise FR-12 rejects it.

### 4.3 Amendment candidates for a future PRD_2 (flagged, not applied)

| ID | Proposed PRD change | Why | Blocks anything? |
|---|---|---|---|
| A-1 | Data section: football-data.co.uk is used for **3-season history and shots for all nine domestic leagues**, not only SPL | GR-04 | Live ingestion of co.uk is blocked until the legal register (§9.8) is signed off. [Rev-1] The terms check itself happens during Stage 1 so a negative answer is known early (ADR-032); the decision stays Divine's. **DECIDED 2026-10-16 [Rev-2, ADR-035]:** path 1 (preferred): if the Stage 1 terms check confirms that downloading the files by hand for personal use is allowed, Divine downloads them and loads them with `footy load-csv`; co.uk is never fetched automatically. Path 2 (fallback): football-data.org only, and the Scottish Premiership is dropped from v1. **OUTCOME 2026-10-16/17 [Rev-3]: Divine chose path 2** (signed in `docs/legal/source_terms_register.md`): football-data.org only, football-data.co.uk is not used at all (no hand downloads, no `footy load-csv`), the Scottish Premiership is dropped. The free plan was measured to return all three seasons asked for (§16), so history does not start empty |
| A-2 | Security section: "The Cloudflare API token used by Actions is scoped to D1 only" → two tokens: **nightly workflow = D1-only**; **deploy workflow = Workers-scripts + D1 migrations scope, in a protected `production` environment** | Wrangler deploy cannot work with a D1-only token | No (ADR-018). **ACCEPTED 2026-10-16 [Rev-2].** Environments are unavailable on Free private repos, so `CF_DEPLOY_TOKEN` is a repo secret referenced only by `deploy.yml` (§9.7) |
| A-3 | Deployment: move the cron from `0 1 * * *` to a non-top-of-hour minute such as `17 1 * * *` | GitHub documents that scheduled runs can be delayed at high-load times such as the top of the hour; 01:00 UTC is exactly that | No — watchdog covers a late run. **ACCEPTED 2026-10-16 [Rev-2, ADR-036]** |
| A-4 | Non-functional: reply latency is not stated. Suggest "reply within 30 s of upload at p95" | Gives a testable target | No. **ACCEPTED 2026-10-16 [Rev-2, ADR-036]:** p95 ≤ 30 s, NFR-11 (the §14 wording of 15 s is superseded) |

---

## 5. Data model (design phase 4)

Engine: **Cloudflare D1 (SQLite)**. All timestamps are UTC ISO-8601 text (`YYYY-MM-DDTHH:MM:SSZ`); all dates `YYYY-MM-DD`. Booleans are `INTEGER 0/1`. Probabilities are `REAL` stored at full precision (display rounding is a presentation concern). Foreign keys are declared; D1 enforces them.

Schema ownership: **SQL migrations in `/db/migrations/` applied by `wrangler d1 migrations apply`** are the single owner of the schema. Both the TypeScript repository and the Python repository are *clients* of it. Migrations are additive-first (see the locked block). **[Rev-1, ADR-033] Each stage creates the tables it first needs**: Stage 1 `0001` creates only `processed_updates`, `uploads`, `events`, `job_runs`; Stage 2 adds `competitions`, `teams`, `team_aliases`, `matches`, `source_fetch_log`; Stages 3-4 add `model_runs`, `active_run`, `model_params`, `team_form`; **[v2]** Stage 5a adds `fixture_forecasts` (`0004`), Stage 5b adds `predictions`, `omissions` (`0005`); Stage 6 adds `calibration_snapshots` (`0006`). The design now has seventeen tables; only the creation order and the new table differ from version 1.

### 5.1 Entity-relationship diagram

```mermaid
erDiagram
    competitions ||--o{ matches : "has"
    teams ||--o{ team_aliases : "known as"
    teams ||--o{ matches : "home/away"
    model_runs ||--o{ model_params : "contains"
    model_runs ||--o{ team_form : "snapshots"
    model_runs ||--o| active_run : "pointed to by"
    model_runs ||--o{ fixture_forecasts : "forecast for"
    fixture_forecasts ||--o| predictions : "copied into"
    uploads ||--o{ predictions : "yielded"
    uploads ||--o{ omissions : "yielded"
    teams ||--o{ predictions : "home/away"
    teams ||--o{ team_form : "form of"

    competitions {
        text comp_code PK
        text name
        text fd_code
        text uk_div
        int has_shots
    }
    teams {
        int team_id PK
        text canonical_name UK
        text home_comp
        int is_ucl_only
        int active
    }
    team_aliases {
        int alias_id PK
        text source
        text alias_norm
        int team_id FK
    }
    matches {
        int match_id PK
        text comp_code FK
        text season
        text match_date
        text kickoff_utc
        int home_team_id FK
        int away_team_id FK
        text status
        int goals_home
        int goals_away
        text result_basis
        int shots_home
        int shots_away
        int fd_match_id UK
    }
    model_runs {
        text run_id PK
        text status
        text data_cutoff_utc
        text config_json
        text ensemble_json
    }
    active_run {
        int id PK
        text run_id FK
        text activated_at
    }
    model_params {
        text run_id PK
        text model PK
        text status
        text payload_json
        text payload_sha256
    }
    team_form {
        text run_id PK
        int team_id PK
        int n_training
        int n_season
    }
    fixture_forecasts {
        text run_id PK
        text fixture_key PK
        text comp_code
        text match_date
        int home_team_id
        int away_team_id
        text verdict
        real p_home
        real p_draw
        real p_away
    }
    uploads {
        int upload_id PK
        int update_id UK
        text file_sha256
        text status
    }
    predictions {
        int pred_id PK
        text fixture_key UK
        int upload_id FK
        text run_id FK
        real p_home
        real p_draw
        real p_away
        text status
    }
    omissions {
        int omission_id PK
        int upload_id FK
        text reason_code
    }
```

Operational tables with no foreign-key relationships (not drawn): `processed_updates`, `source_fetch_log`, `job_runs`, `events`, `calibration_snapshots`.

### 5.2 Reference tables

**`competitions`** — 10 rows, seeded.

| Column | Type | Constraint / note |
|---|---|---|
| comp_code | TEXT | PK. One of `EPL, LL, BL, SA, L1, UCL, ERE, PPL, CHA, SPL` |
| name | TEXT | NOT NULL |
| fd_code | TEXT | football-data.org code: `PL, PD, BL1, SA, FL1, CL, DED, PPL, ELC`; NULL for SPL |
| uk_div | TEXT | football-data.co.uk division file: `E0, SP1, D1, I1, F1, N1, P1, E1, SC0`; NULL for UCL |
| has_shots | INTEGER | 1 for the nine domestic leagues, 0 for UCL |

**`teams`** — 179 active rows seeded from `data/canonical_teams.json`, plus ≈ 60 history-only rows (`active=0`) seeded from `data/historical_teams.json` [Rev-1, ADR-027].

| Column | Type | Constraint / note |
|---|---|---|
| team_id | INTEGER | PK |
| canonical_name | TEXT | UNIQUE NOT NULL — exactly the PRD canonical spelling |
| home_comp | TEXT | FK `competitions`; NULL for UCL-only clubs |
| is_ucl_only | INTEGER | 0/1 |
| active | INTEGER | 1 for the 2026–27 list; 0 for history-only clubs (from `data/historical_teams.json`, or a club that later left the list) so history still joins [Rev-1] |

**`team_aliases`** — one row per (source spelling → team).

| Column | Type | Constraint / note |
|---|---|---|
| alias_id | INTEGER | PK |
| source | TEXT | CHECK in (`fd_org`, `fd_uk`, `screener`, `manual`) |
| alias_norm | TEXT | Normalised spelling: NFKD, accents stripped, lower-case, punctuation → space, whitespace collapsed |
| team_id | INTEGER | FK `teams` NOT NULL |
| | | UNIQUE (`source`, `alias_norm`) |

An alias that resolves to two teams is impossible by the unique key. A source spelling with no row is **unmapped** (reported, never guessed).

### 5.3 Results data

**`matches`**

| Column | Type | Constraint / note |
|---|---|---|
| match_id | INTEGER | PK |
| comp_code | TEXT | FK, NOT NULL |
| season | TEXT | e.g. `2026-27` (Aug–May) |
| match_date | TEXT | UTC calendar date, NOT NULL |
| kickoff_utc | TEXT | NULL for co.uk-only rows without a time |
| home_team_id, away_team_id | INTEGER | FK `teams`, NOT NULL, CHECK different |
| status | TEXT | CHECK in `SCHEDULED, TIMED, IN_PLAY, FINISHED, POSTPONED, CANCELLED, SUSPENDED, AWARDED` |
| goals_home, goals_away | INTEGER | **90 minutes plus stoppage time only.** NULL until `FINISHED`. CHECK 0..20 |
| result_basis | TEXT | CHECK in `regular`, `ft_90`, `unverified` — how the 90-minute score was obtained (ADR-010) |
| shots_home, shots_away | INTEGER | NULL when unavailable; not populated or used in v1 (ADR-026) [Rev-1] |
| fd_match_id | INTEGER | UNIQUE, NULL for co.uk-only rows |
| uk_key | TEXT | co.uk natural key (division/date/teams) for idempotent upsert |
| goals_source | TEXT | `fd_org` or `fd_uk` |
| updated_at | TEXT | |
| | | UNIQUE (`comp_code`, `season`, `match_date`, `home_team_id`, `away_team_id`) |
| | | Indexes: (`home_team_id`, `match_date`), (`away_team_id`, `match_date`), (`comp_code`, `match_date`), (`status`, `match_date`) |

**`source_fetch_log`** — audit of every external fetch (also the cache metadata for conditional GETs).

| Column | Type |
|---|---|
| fetch_id (PK), source, resource, fetched_at, http_status, ok (0/1), etag, last_modified, content_sha256, rows, bytes | |

### 5.4 Model registry (the "model registry" of RESOURCE 3)

**`model_runs`** — immutable once `active` (only `status` may change afterwards).

| Column | Type | Note |
|---|---|---|
| run_id | TEXT | PK, `R` + UTC timestamp, e.g. `R20261016T011742Z` |
| status | TEXT | CHECK in `building, active, superseded, rejected, failed` |
| started_at, finished_at | TEXT | |
| data_cutoff_utc | TEXT | Latest result included; the stale-run guard compares to it |
| training_from, training_to | TEXT | Window actually used |
| git_sha, code_version | TEXT | Reproducibility |
| config_json | TEXT | **Snapshot** of thresholds (drift, minimum matches, stale hours), league baselines (H/D/A and over frequencies) and flags such as `"unvalidated": true` |
| ensemble_json | TEXT | Weights per model, method, number of scored matches used |
| diagnostics_json | TEXT | Convergence stats, sanity-check results, row counts, unmapped teams |

**`active_run`** — exactly one row.

| Column | Type | Note |
|---|---|---|
| id | INTEGER | PK, CHECK (id = 1) |
| run_id | TEXT | FK `model_runs` |
| activated_at | TEXT | |

**`model_params`**

| Column | Type | Note |
|---|---|---|
| run_id, model | TEXT | Composite PK; `model` CHECK in `dc, pi, bp` |
| status | TEXT | CHECK in `ok, failed` |
| payload_version | INTEGER | Lets the bot reject payloads it does not understand (additive evolution) |
| payload_json | TEXT | Per-model parameters for all teams (≈ 30–60 KB) |
| payload_sha256 | TEXT | Integrity check on read |
| error | TEXT | Failure reason when `failed` |

**`team_form`** — per run, per team (drives the drift filter and the "< 10 matches" rule without recomputing on the Worker).

| Column | Type |
|---|---|
| run_id, team_id | PK pair |
| n_training | matches inside the training window |
| n_season | matches in the current season |
| season_gf, season_ga | goals for/against per match this season |
| l10_n, l10_gf, l10_ga | last-10 window |
| shots_n, season_sf, season_sa, l10_sf, l10_sa | shots; NULL in v1 (shots drift deferred, ADR-026) [Rev-1] |
| latest_match_date | Freshness per team |

**[Rev-4]** `team_form` has a row for every active team of the run; a team without matches (for example the dropped Scottish clubs) has `n_training = 0` and NULL means, and the Worker treats it as INSUFFICIENT_HISTORY. `model_params` also carries a CHECK that an `ok` row has its payload, version and hash. The CHECK lists on `model` and `status` are fixed by this schema: adding a fourth model or a new run status needs a table-rebuild migration, not a plain additive one.

**`fixture_forecasts`** [v2, ADR-042] — written by `footy fit`, read by the Worker; one row per scheduled fixture in the forecast window and run. Created in migration `0004`.

| Column | Type | Note |
|---|---|---|
| run_id | TEXT | FK `model_runs`; with `fixture_key` the composite PK |
| fixture_key | TEXT | `<match_date>\|<comp>\|<home_team_id>\|<away_team_id>` (the §8.7 key) |
| comp_code, match_date, kickoff_utc, home_team_id, away_team_id | | `match_date` is the UTC calendar date of kickoff; the team ids are FKs `teams` |
| verdict | TEXT | CHECK in `ok, INSUFFICIENT_HISTORY, DRIFT, NO_MODEL` |
| p_home, p_draw, p_away | REAL | Ensemble, full precision. NULL unless `verdict='ok'`; CHECK sum within 1e-6 of 1 |
| p_over_05, p_over_15, p_over_25, p_over_35, p_over_45, p_over_55 | REAL | Ensemble, full precision; NULL unless `ok`; CHECK monotone non-increasing (tolerance 1e-9) |
| total_json | TEXT | Ensemble total-goals pmf, 13 categories (0..11, 12+) |
| models_json | TEXT | Per model that produced a grid: `{"p": [home, draw, away], "total": [13 values]}` |
| weights_json | TEXT | Weights applied (the run's weights over the models that produced a grid, renormalised) |
| baseline_json | TEXT | League-frequency forecast for the competition (1X2, overs, total pmf) from the run's baseline snapshot |
| detail_json | TEXT | NOT NULL. Drift statistics and thresholds, team history counts, models left out and why |
| created_at | TEXT | |
| | | Index (`run_id`, `match_date`). CHECK: an `ok` row has every probability, `total_json`, `models_json`, `weights_json` and `baseline_json` |

Forecast rows are immutable once written (`INSERT OR IGNORE`); they are kept for the newest 5 servable runs (`active`, `superseded`, `building`; a rejected or failed run takes no slot) and deleted with an older run; the active run's are never deleted (§8.11).

### 5.5 Prediction log

**`uploads`**

| Column | Type | Note |
|---|---|---|
| upload_id | INTEGER | PK |
| update_id | INTEGER | UNIQUE — Telegram update id |
| received_at | TEXT | |
| tg_file_unique_id, file_sha256, size_bytes | | |
| run_date_utc | TEXT | From the file, if parsed |
| schema_version | INTEGER | |
| n_matches_in, n_excluded_in, n_published, n_omitted, n_duplicate | INTEGER | |
| run_id | TEXT | Active run used |
| status | TEXT | CHECK in `received, rejected, processed, failed`. **[Rev-1, ADR-029]** The row is inserted as `received` before any heavy work, so an upload that is never finalised can be found by the watchdog |
| error_code | TEXT | From the error catalogue (§6.6) |

**`predictions`** — one row per published fixture; **immutable except for result/scoring columns**.

| Column | Type | Note |
|---|---|---|
| pred_id | INTEGER | PK |
| fixture_key | TEXT | **UNIQUE** — `<kickoff_date_utc>\|<comp>\|<home_team_id>\|<away_team_id>` |
| upload_id, run_id | | `upload_id` is a FK. [v2, ADR-045] `run_id` is a plain column, not a FK: a prediction copies everything it needs, so runs can be pruned while their predictions stay |
| label | TEXT | The screener's `match_id`, display only |
| comp_code, kickoff_utc, home_team_id, away_team_id | | `kickoff_utc` is the screener's time; [v2] also `match_date` TEXT NOT NULL (the UTC kickoff date, the first part of `fixture_key`) |
| p_home, p_draw, p_away | REAL | NOT NULL, stored at full precision (not rounded); CHECK sum within 1e-6 of 1 [Rev-1] |
| p_over_05, p_over_15, p_over_25, p_over_35, p_over_45, p_over_55 | REAL | NOT NULL, full precision [Rev-1] |
| total_json | TEXT | [v2, replaces `grid_json`] The ensemble total-goals pmf (13 categories) copied from the forecast; with the 1X2 and over columns it makes every metric recomputable without a grid |
| models_json | TEXT | Per model: 1X2 and the total-goals pmf (copied from the forecast) — used for rolling per-model RPS |
| weights_json | TEXT | Weights actually applied (after dropping failed models) |
| drift_json | TEXT | Drift statistics and verdict copied from the forecast's `detail_json`; [v2] `baseline_json` TEXT NOT NULL is the league-frequency forecast copied from the forecast row, so the baseline comparison needs no run |
| inputs_json | TEXT | Screener fields: lineup_status, absences, rest days, source URLs, note |
| status | TEXT | CHECK in `pending, scored, void` |
| void_reason | TEXT | `POSTPONED`, `CANCELLED`, `SUSPENDED`, `AWARDED`, `UNVERIFIED_RESULT`, `NO_RESULT` (added Rev-1, ADR-028) |
| goals_home, goals_away | INTEGER | Filled when scored (90-minute basis) |
| rps_1x2, rps_totals, logloss_1x2 | REAL | Filled when scored |
| created_at, scored_at | TEXT | |
| | | Indexes: (`status`, `kickoff_utc`), (`comp_code`, `kickoff_utc`) |

**`omissions`** — matches in a file that did not produce a prediction.

| Column | Type | Note |
|---|---|---|
| omission_id | INTEGER | PK |
| upload_id | INTEGER | FK |
| label | TEXT | The screener's `match_id` |
| reason_code | TEXT | `UNMAPPED_TEAM, INSUFFICIENT_HISTORY, DRIFT, STARTED, TOO_FAR, DATE_MISMATCH, NO_MODEL, DUPLICATE_PAIR, NO_FORECAST` ([v2] `NO_FORECAST` added) |
| detail_json | TEXT | |
| | | UNIQUE (`upload_id`, `label`) |

**`processed_updates`** — Telegram dedupe. `update_id` PK, `received_at`, `kind`, `outcome`.

### 5.6 Operations

| Table | Purpose | Key columns |
|---|---|---|
| `job_runs` | One row per nightly/backtest/report/bootstrap job | `job_id`, `kind`, `started_at`, `finished_at`, `status`, `git_sha`, `summary_json`, `error` |
| `events` | Durable, compact structured events (alerts raised, unmapped teams, anomalies, ignored chats count). Pruned at 90 days | `event_id`, `at`, `level`, `source`, `kind`, `detail_json`, `dedupe_key` |
| `calibration_snapshots` | Weekly metrics for history | `snapshot_id`, `created_at`, `window_from`, `window_to`, `n_scored`, `metrics_json`, `run_id` |

### 5.7 Invariants (enforced in code and tests)

1. `active_run.run_id` always refers to a `model_runs` row with `status='active'` and at least one `model_params` row with `status='ok'`.
2. Exactly one `predictions` row per `fixture_key`; its probability columns are never updated.
3. `goals_*` in `matches` are 90-minute scores or NULL; `result_basis='unverified'` rows are excluded from training and scoring.
4. Every probability row satisfies `p_home + p_draw + p_away = 1 ± 1e-6` and `p_over_05 ≥ p_over_15 ≥ … ≥ p_over_55`.
5. A run is promoted (`active_run` updated) only after its sanity checks pass (§8.6).
6. [Rev-1] An `uploads` row still `received` after 10 minutes raises an alert (§9.2).
7. [v2] A `fixture_forecasts` row with `verdict='ok'` satisfies the same sum and monotonicity checks as a prediction; the Worker never writes `fixture_forecasts`, and the fit job never writes `predictions` except to fill in results (`footy score`).
8. [v2] A prediction's probability columns equal the forecast row it was copied from at insertion time, and never change afterwards.
9. [v3] The command path (§6.10) writes no row to `predictions`, `omissions`, `uploads`, `fixture_forecasts`, `model_runs`, `active_run`, `team_form` or `calibration_snapshots`; its only writes are the `processed_updates` dedupe row and a `command_failed` event.

---

## 6. API / interface layer (design phase 5)

This system has no public REST API. Its interfaces are: (I-1) the screener file contract, (I-2) the Telegram inbound webhook, (I-3) Telegram outbound calls, (I-4) internal TypeScript module interfaces, (I-5) the Python CLI, (I-6) external data APIs consumed, (I-7) D1 access paths, [v3] (I-8) bot commands (§6.10).

### 6.1 I-1 — Screener file contract, schema version 1 (Zod on the Worker; JSON Schema copy in `packages/contracts`)

| Field | Type / rule |
|---|---|
| `schema_version` | literal `1` — anything else → `E_SCHEMA_VERSION` |
| `run_date_utc` | `YYYY-MM-DD`, a real calendar date |
| `notes` | string ≤ 2,000 chars, or `null` |
| `matches` | array, 0–100 items |
| `matches[].match_id` | string 1–160 chars; **opaque label** |
| `matches[].competition` | enum: `EPL, LL, BL, SA, L1, UCL, ERE, PPL, CHA, SPL` |
| `matches[].home`, `.away` | string 1–64; canonical name; must differ |
| `matches[].kickoff_utc` | `YYYY-MM-DDTHH:MM:00Z`, valid instant |
| `matches[].lineup_status` | enum `none, expected, confirmed` |
| `matches[].absences_home`, `.absences_away` | `null` or array ≤ 40 of `{player: string ≤ 80, status: "out"\|"doubtful", source_url: https URL ≤ 300}` |
| `matches[].rest_days_home`, `.rest_days_away` | integer 0–60, or `null` |
| `matches[].source_urls` | array ≤ 20 of https URLs ≤ 300 |
| `excluded` | array ≤ 200 of `{match: string ≤ 200, reason: string ≤ 40}`; unknown reasons are kept and counted as `OTHER` |

Rules:
- Unknown extra keys are stripped, not fatal (so a harmless prompt change does not brick the day); a **missing or mistyped required key** is fatal.
- Contract evolution: any change that is not purely additive-optional becomes `schema_version: 2` handled by a *new* parser alongside v1 (never mutate v1).
- Never rendered raw: `notes`, player names and URLs are length-capped and escaped when echoed (prompt-injection / formatting-injection defence).
- Business checks after parsing (each produces an omission, not a file rejection): kickoff date equals `run_date_utc`; kickoff strictly after *now* and ≤ now + 48 h; both teams resolve to `teams`; home ≠ away.

### 6.2 I-2 — Telegram inbound webhook

| Aspect | Definition |
|---|---|
| Endpoint | `POST /tg/<WEBHOOK_PATH_SECRET>` on the Worker. Every other path/method → `404` |
| Registration | `setWebhook` with `secret_token`, `allowed_updates=["message"]`, `drop_pending_updates=false` — run once by `scripts/set-webhook` and re-checked in post-deploy smoke |
| Header | `X-Telegram-Bot-Api-Secret-Token` must equal `TELEGRAM_WEBHOOK_SECRET` (constant-time compare) else `401` |
| Allowed sender | private chat whose `chat.id == ALLOWED_CHAT_ID` and `from.id == ALLOWED_USER_ID` — anything else → `200` with no reply, one counter event |
| Update kinds | `message.document` → intake pipeline; [v3] a `message.text` starting with `/` → command router (§6.10), `processed_updates.kind = 'command'`; any other allowed-sender message → usage hint |
| Response | Always `200` quickly once authenticated (so Telegram does not retry); work continues in `ctx.waitUntil`. [Rev-1] The `uploads` row is inserted with status `received` before any heavy work (ADR-029) |

### 6.3 Behaviour matrix (what Divine sees)

| Situation | Bot reply | Logged |
|---|---|---|
| Valid file, all matches pass | 1+ messages with probabilities + footer | `uploads`, `predictions` |
| Valid file, some omitted | Probabilities for the rest + "Omitted:" list with reasons | + `omissions` |
| Valid file, zero matches | "File valid: 0 matches passed the screener (N excluded: …)" | `uploads` |
| Fixture already logged | Same numbers from the log, marked "already logged" | `uploads` (n_duplicate) |
| Not `.json`, wrong size, not JSON, bad schema, wrong version | One error message naming the problem (first ≤ 5 validation paths, no file content echoed) | `uploads` (rejected) |
| Telegram file download fails | "Could not download the file. Please resend." | `uploads` (failed) |
| No active model run / all models failed | "No usable model run — nothing computed." | event + alert |
| Text or other message from Divine | "Upload the screener .json file as a document." [v3] plus a second line "Send /help to see the commands." | none |
| Any message from another chat | nothing | counter event only |
| Active run older than 36 h | Normal reply with a **STALE MODELS** banner | event |
| [Rev-1] Upload acknowledged but never answered (for example Worker killed at the CPU limit) | No reply; alert to Divine within about 6 h | `uploads` stays `received`, event + alert |
| [v2] Match not found among the stored forecasts | Listed under "Omitted:" with reason `NO_FORECAST`; nothing computed | `omissions` |
| [v2] Forecast says INSUFFICIENT_HISTORY / DRIFT / NO_MODEL | Listed under "Omitted:" with that reason and the numbers from the forecast | `omissions` |
| [v2] Run has no forecast rows at all for the date | Normal reply, every match `NO_FORECAST`, banner "no forecasts stored for this run" | event |
| [v3] A known command from Divine | The command's reply (§6.10) | `processed_updates` (kind `command`) only |
| [v3] An unknown command from Divine | "Unknown command. Send /help to see the commands." | `processed_updates` only |
| [v3] A command with an invalid argument (bad date, out of range, over 64 characters) | The command's usage line, for example "Usage: /fixtures [today\|tomorrow\|YYYY-MM-DD], a date from today to today + 4" | `processed_updates` only |
| [v3] A command fails unexpectedly | "Internal error, id=…" | `command_failed` event |
| [v3] A command from another chat | nothing | counter event only (as any message) |

### 6.4 I-3 — Telegram outbound

| Call | Use | Notes |
|---|---|---|
| `getFile`, then file download | Fetch the upload | Download URL contains the bot token → never logged |
| `sendMessage` | Replies, split ≤ 3,900 chars at match boundaries | Plain text (no Markdown parsing → no escape failures); 429 handling with `retry_after` if ≤ 5 s |
| `sendPhoto` | Weekly calibration chart from the fit job | Optional in Phase 6 |
| `setMyCommands` [v3] | Register the "/" command menu at deploy (`scripts/set-webhook.mjs`, ADR-052) | `scope: {type: "chat", chat_id}` with the allowlisted chat; list from `packages/contracts/bot_commands.json`; a failure or a missing chat id is a warning, not a failed deploy |

### 6.5 I-4 — Internal module interfaces (TypeScript, in `apps/bot/src`)

Interfaces are the *only* way modules talk; signatures are contracts reviewed in pull requests.

| Module | Interface | Notes |
|---|---|---|
| `auth` | `verifyWebhook(req): Result<Ok, AuthError>`; `checkSession(update): Session \| null` | **The only module that reads webhook secret, chat id or user id.** Locked-block requirement |
| `intake` | `parseScreenerFile(bytes): Result<ScreenerV1, IntakeError>` | Size cap, UTF-8, JSON parse, hand validator (`intake/validate.ts`) kept equal to the Zod contract in `intake/schema.ts` by a differential test (ADR-047) |
| `repo` | `RunRepository`, `PredictionRepository`, `UpdateRepository`, `TeamRepository` (see below) | **The only module that touches D1.** Batched calls |
| `engine` | [v2] **Not built.** Version 1 listed `buildGrid`, `mixGrids`, `markets`; the grids are computed in Python (ADR-042). The spike code under `apps/bot/src/spike` stays, deprecated | |
| `drift` | [v2] **Not built in the Worker.** The verdict is computed by `footy/drift.py` and stored with the forecast (ADR-044) | |
| `format` | `renderReply(results, ctx): string[]` | Pure; splitting included |
| `telegram` | `send(chatId, text)`, `getFile(fileId)`, `download(path, maxBytes)` [v2: plain `fetch`, no grammY, ADR-043; the only module that reads `TELEGRAM_BOT_TOKEN`] | |
| `watchdog` | `scheduled(event, env)` | Cron trigger entry. [v3] Its pure `collectFindings(repos, now)` is also used by `/status` |
| `commands` [v3] | `parseCommand(text) → ParsedCommand \| UnknownCommand` (pure); `handleCommand(deps, chatId, parsed) → CommandOutcome` | Registry from `packages/contracts/bot_commands.json`; reads through `repo.queries` only; renders with `format/commands.ts` (pure); sends through `telegram`. Imports neither `upload/` nor `intake/`; writes nothing (§8.12) |

`repo` surface (names are normative; bodies are Essentials work): `ForecastRepository.readActiveForDate(date) → {pointer, forecasts[], runHasForecasts}` (one consistent batch through the `active_run` pointer) [v2, replaces `RunRepository.loadActive`], `PredictionRepository.insertManyIgnoreDuplicates(rows)` and `findByDate(date)`, `OmissionRepository.insertMany(rows)`, `TeamRepository.resolveCanonical(names) → map`, `UploadRepository.record(upload)` (inserts as `received` first and finalises later; plus `findStale(olderThanMinutes)` for the watchdog) [Rev-1], `UpdateRepository.markProcessed(updateId) → firstTime: boolean`, `EventRepository.record(event)`. `RunRepository.readActive`, `readActiveVerified` and `payloadVerifies` read model payloads the Worker no longer needs; they are **deprecated in v2** (kept, not deleted; removal in a later version once nothing references them).
`RunRepository.loadActive(teamIds) → {run, config, ensemble, params[], forms[]}` (one consistent read), `PredictionRepository.insertManyIgnoreDuplicates(rows)`, `PredictionRepository.findByFixtureKeys(keys)`, `UploadRepository.record(upload)` (inserts as `received` first and finalises later; plus `findStale(olderThanMinutes)` for the watchdog) [Rev-1], `UpdateRepository.markProcessed(updateId) → firstTime: boolean`, `TeamRepository.resolveCanonical(names) → map`, `EventRepository.record(event)`.

[v3] `QueryRepository` (read-only: `SELECT` statements only, each method one batch; names are normative): `activeRunSummary() → {runId, activatedAt, dataCutoffUtc, configJson, ensembleJson, models[{model, status}]} | null` (no payloads); `latestJobs(kinds) → [{kind, status, startedAt, finishedAt}]`; `alertEvents(sinceIso, limit) → {rows[{at, kind, delivered, source}], total}` and `alertPathEvents(sinceIso)` (§6.10 definitions); `forecastVerdicts(date) → {runId, rows[{kickoffUtc, compCode, home, away, verdict}], unforecast} | null`; `settled(limit)` and `pending(limit) → {rows, total}` (predictions with team names); `latestSnapshot() → {createdAt, windowFrom, windowTo, nScored, metricsJson, runId} | null`; `latestUpload() → upload row | null`; `teamCandidates(aliasNorm) → {teams[{id, name, homeComp, active}], aliasTeamIds[]}`; `teamForm(teamId, fromDate) → {form, nextFixture} | null`; `teamNames(ids) → map`. `/logged` reuses `PredictionRepository.findByDate`.

### 6.6 Error catalogue (shared by code, tests, replies, logs)

| Code | Meaning | User-visible | HTTP to Telegram |
|---|---|---|---|
| `E_NOT_JSON_FILE` | Not a `.json` document | yes | 200 |
| `E_TOO_LARGE` | > 256 KB | yes | 200 |
| `E_DOWNLOAD_FAILED` | `getFile`/download failed | yes | 200 |
| `E_PARSE` | Not valid UTF-8 JSON | yes | 200 |
| `E_SCHEMA_VERSION` | `schema_version` ≠ 1 | yes | 200 |
| `E_SCHEMA_INVALID` | Schema validation failure | yes (≤ 5 paths) | 200 |
| `E_NO_RUN` | No usable active run | yes | 200 |
| `E_INTERNAL` | Unexpected exception | yes: "Internal error, id=…" | 200 |
| `E_AUTH` | Bad secret header | no | 401 |

Omission codes are in §5.5. A `Result<T,E>` type is used for expected failures; exceptions are reserved for bugs. [v3] Commands add no code: an unexpected failure is `E_INTERNAL`; an unknown command or a bad argument is a usage reply, not an error.

### 6.7 I-5 — Python CLI (`apps/fit`, entry point `footy`)

| Command | Does | Used by |
|---|---|---|
| `footy bootstrap` | One-off: load canonical teams/aliases, the history-only clubs and 3-season history from the hand-loaded co.uk files (`footy load-csv`) or, in the fallback, from football-data.org (and earlier UCL if the free tier allows) [Rev-2]; writes `matches` through the repo layer in chunked, resumable bound-parameter statements [Rev-1, ADR-031] | Manual workflow |
| `footy load-csv --dir <path>` | [Rev-2, ADR-035] Parse football-data.co.uk CSV files that Divine downloaded by hand into a local folder (never inside the repo); reconcile and upsert `matches` through the repo layer; idempotent; used for the 3-season history and for weekly Scottish Premiership refreshes. Run on Divine's machine with the D1-only token in a local environment variable. Not used under the fallback | Manual, local |
| `footy ingest` | Incremental fetch of football-data.org (last 7 days + next 3); football-data.co.uk is never fetched automatically [Rev-2]; reconcile and upsert | Nightly |
| `footy score` | Fill results into `predictions`; void postponed/cancelled/awarded/unverified and `NO_RESULT` after 3 days [Rev-1]; compute RPS/log loss; idempotent (`WHERE status='pending'`); one deduped alert for the `NO_RESULT` list [v2 detail] | Nightly |
| `footy fit` | Train DC/pi/BP, compute ensemble weights (rolling RPS of logged predictions when they exist [v2]), baselines, `team_form` **and the per-fixture forecasts [v2]**, run sanity checks, write run as `building` | Nightly |
| `footy publish` | Atomically promote the run (`active_run`) if it passed the checks; mark previous `superseded`; prune | Nightly |
| `footy report [--send] [--monday-only]` | Weekly calibration summary (+ chart); writes a `calibration_snapshots` row; sends to Telegram with `--send` (needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`) [v2 detail] | Monday |
| `footy backtest` | Walk-forward evaluation; [v2] `--fail-on-regression` compares the result with the previous comparable stored backtest and exits 4 beyond a tolerance of 0.003 RPS (informational, not a deploy block) | Monthly / manual |
| `footy healthcheck` | Run-age and freshness checks (used by humans and CI smoke) | Manual |
| `footy alert --text` | Send a Telegram alert (used on workflow failure) | Workflow `if: failure()` |

Exit codes: `0` ok, `2` data/validation failure, `3` source outage (cached data used), `4` fit failure (partial), `1` unexpected. Workflows alert on non-zero.

**[Rev-4]** As built: `footy backtest [--models dc,pi,bp] [--test-days N] [--fold-days N] [--half-lives a,b] [--shrinks a,b] [--out FILE]` (needs only D1; writes a `job_runs` row, the readable report goes to stderr); `footy fit [--models ...] [--as-of YYYY-MM-DD]`; `footy publish [--run-id ID [--accept-drift] | --rollback ID]`. Model commands need only the D1 variables; the football-data.org legal gate applies to `bootstrap` and `ingest` only. A gate rejection, a failed model and a backtest with a failed fold all exit with code 4.
**[v2]** `footy fit` also writes the forecasts; `footy publish` also checks them (§8.6) and prunes forecasts of runs beyond the newest 5; `footy score [--as-of]`; `footy report [--send] [--monday-only]`; `footy backtest ... [--fail-on-regression] [--regression-tolerance X]`.

### 6.8 I-6 — External APIs consumed

| Source | Used for | Details |
|---|---|---|
| football-data.org v4 | Fixtures, results, UCL, team lists | `GET /v4/competitions/{code}/matches?dateFrom=&dateTo=`; header `X-Auth-Token`; free tier 10 requests/minute; fields used: `id, utcDate, status, homeTeam.name, awayTeam.name, score.duration, score.fullTime, score.regularTime`; competition codes in §5.2 |
| football-data.co.uk | History, shots, SPL | CSV per division per season, e.g. `mmz4281/2526/E0.csv`; columns used: `Div, Date, Time (if present), HomeTeam, AwayTeam, FTHG, FTAG, HS, AS` (**verify headers at build**); read from local files that Divine downloads by hand and loads with `footy load-csv`; never fetched automatically [Rev-2, ADR-035] |
| Telegram Bot API | See I-2/I-3 | |
| Cloudflare D1 REST API | Python → D1 | `POST /accounts/{id}/d1/database/{db}/query`; D1-only token; ≤ 100 bound parameters per statement; bulk bootstrap uses chunked multi-row bound-parameter statements through `d1_client.py` (resumable), never SQL files with literal values [Rev-1, ADR-031] |

### 6.9 I-7 — D1 access paths

| Client | Path | Rule |
|---|---|---|
| Worker | D1 binding, through `apps/bot/src/repo/*` only | Parameterised statements only; `batch()` for multi-statement reads/writes |
| Fit job | D1 REST through `apps/fit/src/footy/repo/d1_client.py` only | Retries with backoff; single place for SQL |
| Schema | `wrangler d1 migrations apply` | Only in deploy workflow / manual workflow |

### 6.10 I-8 — Bot commands [v3, ADR-049 to ADR-052]

Read-only commands answered to the allowlisted chat. They run after the same three auth layers and the same `update_id` dedupe as an upload (§7.8), in `ctx.waitUntil` after the acknowledgement, and they only read stored rows.

**Grammar.**
- A command is a `message.text` whose first character is `/`. A document always goes to the upload pipeline, even when its caption starts with `/`.
- The token is the text up to the first whitespace. A `@<bot username>` suffix is removed, the token is lower-cased and must match `^/[a-z_]{1,32}$`; anything else is an unknown command.
- The arguments are the rest of the text: control and direction characters removed, whitespace collapsed, trimmed. More than 64 characters gives that command's usage line and nothing is read.
- `/start` is an alias of `/help` (Telegram sends it when a chat is opened).
- Arguments are never echoed in a reply, a log line or an event. A command name is logged only when it is a known one.

**Dates.** `today`, `tomorrow`, `yesterday` or `YYYY-MM-DD` (a real calendar date), case-insensitive, read as **UTC calendar dates**: the dates of `run_date_utc`, `match_date` and `fixture_key`. No argument means `today`. An unreadable date gives the command's usage line. Kickoff times are rendered in UTC and IST with the `+1d` rule of §8.8.

**The list of commands has one source**, `packages/contracts/bot_commands.json` (name, argument hint, one-line description), read by the Worker's registry and by `scripts/set-webhook.mjs` for Telegram's menu (ADR-052). A test fails if the registry and the file differ.

| Command | Arguments | Reads (through `QueryRepository`, read-only) | Reply |
|---|---|---|---|
| `/help`, `/start` | none | nothing | One line per command from `bot_commands.json`, then "Probabilities come only from an uploaded screener file." |
| `/status` | none | The watchdog's `collectFindings` (the same pure function the cron uses: no active run, stale run, no forecasts for today or tomorrow while fixtures are scheduled, stuck uploads); the active run summary (run id, `activated_at`, `data_cutoff_utc`, stale limit from `config_json`, weights from `ensemble_json`, `model_params.status` per model, never a payload); the newest `job_runs` row of each kind `ingest`, `score`, `fit`, `publish`, `healthcheck`; the coverage of today and tomorrow (`HealthRepository.forecastCoverage`); the undelivered alert events of the last 48 h; the alert-path events of the last 24 h (`bot_token_missing`, `alert_chat_invalid`, `alert_send_failed`, `watchdog_failed`, the nightly health check's fifth check) | Headline `OK` when there is no finding, no failed model in the active run, no failed newest nightly step and no alert-path event; otherwise `ATTENTION`, with the findings' text first. Then one line each: run id and age against its limit, data cut-off, models and weights, each nightly step (status and UTC start time), coverage per day (forecasts / scheduled), stuck uploads, alerts waiting for the nightly delivery, alert-path problems |
| `/fixtures [date]` | a date from today to today + 4 (the forecast window, `forecast.horizon_days`) | The active run's `fixture_forecasts` for the date with team names from `teams`; the number of `matches` rows `SCHEDULED` or `TIMED` on that date with no forecast row in the active run | Header: date (UTC), run id, counts by verdict. One line per fixture by kickoff, competition and home name: `EPL  Arsenal vs Chelsea  15:00 UTC (20:30 IST)  ok`. Then "N scheduled fixtures have no forecast (an upload would answer NO_FORECAST)" when N > 0. Footer: "Verdicts only. Probabilities come from an uploaded screener file; its gates still decide." **No probability, percentage or model number is printed (ADR-050).** Outside the window: "Forecasts are stored for <today> to <today + 4> (UTC dates)." No active run: "No model run is published." |
| `/logged [date]` | any date | `predictions` with that `match_date` (`PredictionRepository.findByDate`), names from `teams` | The §8.8 match block of each prediction (the stored numbers, as the upload reply showed them), with its status (`pending`, `scored 2-1`, `void NO_RESULT`) and the UTC time it was logged. "Nothing logged for <date>." when empty |
| `/results [n]` | an integer 1–20, default 10 | the newest `n` predictions with status `scored` or `void`, by `kickoff_utc` descending, names from `teams` | One line each: competition, teams, kickoff date, the 90-minute score, the logged H/D/A with the actual outcome marked, the stored `rps_1x2`; a void row shows its reason. Stored values only: no average is computed (that is `/report`) |
| `/pending` | none | `predictions` with status `pending` by `kickoff_utc` ascending (at most 30) and their total count | One line each: competition, teams, kickoff (UTC and IST); "and N more" beyond 30 |
| `/report` | none | the newest `calibration_snapshots` row | Created time, window, scored / target and pending; the paired 1X2 RPS of the ensemble and the baseline, the mean difference and its interval and level; RPS per model; the omission rate and counts by reason. Values are the snapshot's, rounded for display; a missing key shows `n/a`. "No weekly report stored yet." when there is none. The chart is not sent (it is drawn in Python and pushed on Mondays, ADR-016) |
| `/last` | none | the newest `uploads` row | Received time (UTC), status, `run_date_utc`, counts (in, excluded, published, omitted, already logged), run id, error code. A row still `received` after 10 minutes adds "never answered: send the file again" |
| `/team <name>` | required, 2–64 characters | all `teams` rows (id, canonical name, home competition, active) and the `team_aliases` rows whose `alias_norm` equals the normalised argument, in one batch; then the active run's `team_form` row of the chosen team and its earliest `fixture_forecasts` row from today in the active run | Canonical name, competition, active or history-only; matches in the training window and this season; goals for and against per match this season and over the last 10 (with the count); latest match date; the next stored fixture (date, opponent, verdict). There is no team-level drift verdict: the rule lives in Python (ADR-044), so the verdict shown is the stored fixture's. Not found: "No team by that name in our table. Use the canonical name, for example /team Arsenal." Several: up to 5 canonical names from our table |
| `/alerts` | none | the alert events of the last 48 h (definition below), newest first, at most 20, and their total | One line each: UTC time, kind, and `delivered`, `waiting` (for the nightly delivery) or `sent by watchdog`; counts by kind. `detail_json` is not shown (it can hold source text) |

**Alert events.** (a) The events `footy alert --flush` delivers, with the same predicate as `OpsRepo.pending_alerts`: `level = 'alert'`, or `kind` in (`unmapped_team`, `canonical_update_needed`), or `kind LIKE 'anomaly\_%'`; delivered when `delivered_at` is set. (b) The watchdog's findings (`watchdog_no_active_run`, `watchdog_stale_run`, `watchdog_no_forecasts`, `watchdog_stuck_upload`), which are recorded only after Telegram accepted them. The TypeScript kind lists are constants next to the query; a repository check compares list (a) with `_WARN_ALERT_KINDS` in `apps/fit/src/footy/repo/ops.py` and list (b) with the watchdog's finding kinds, so the definitions cannot drift apart silently.

**`/report` read contract.** The Worker reads these keys of `calibration_snapshots.metrics_json` (written by `footy/report/metrics.py`): `n_scored`, `n_pending`, `target`, `paired.{n, ensemble_rps_1x2, baseline_rps_1x2, mean_diff_rps_1x2, ci_low, ci_high, level}`, `by_model.<name>.{n, rps_1x2}`, `omissions.{rate, by_reason}`. A pytest pins that `compute_metrics` returns them; renaming one is a breaking change of this contract (Extensibility rule, API), so a new key is added beside the old one.

**Limits.** At most 2 D1 batch calls and at most 5 reply messages per command (split by `splitBlocks` / `packLines`, §8.8); no `getFile`, no download, no file validation.

---

## 7. High-level architecture (design phase 6)

Architecture style: **two-runtime batch-fit / online-serve system around one SQLite database**, no servers to operate. Diagrams follow the C4 model (Context → Container → Component; Level 4 is the ER diagram in §5 and the interface tables in §6), as required by the project's C4 resource.

### 7.1 C4 Level 1 — System context

```mermaid
C4Context
    title System Context - Football Reliability Screener and Probability Bot

    Person(divine, "Divine", "Sole user. Runs the daily screen, uploads the file, reads probabilities.")
    System(sys, "Screener and Probability Bot", "Fits models and computes per-fixture forecasts nightly; on upload validates, looks up the stored forecasts and replies; logs and scores every prediction.")
    System_Ext(claude, "Claude Project (screener)", "Manual hand-off. Lists fixtures, applies gates G1-G6, outputs a schema-v1 .json file.")
    System_Ext(tg, "Telegram Bot API", "Only user interface. Webhook in, messages out, file download.")
    System_Ext(fdorg, "football-data.org v4", "Fixtures, results, Champions League. Free tier.")
    System_Ext(fduk, "football-data.co.uk", "CSV history, shots, Scottish Premiership.")
    System_Ext(web, "League, UEFA and soccernews.com pages", "Read by the Claude Project only, never by this system.")

    Rel(divine, claude, "Sends run today, receives .json file")
    Rel(divine, tg, "Uploads .json, reads replies and alerts")
    Rel(tg, sys, "Webhook updates", "HTTPS")
    Rel(sys, tg, "Replies, alerts, file download", "HTTPS")
    Rel(sys, fdorg, "Nightly fixtures and results", "HTTPS, token")
    Rel(divine, fduk, "Downloads CSV files by hand (path 1 of A-1)", "browser")
    Rel(claude, web, "Reads pages normally")
```

### 7.2 C4 Level 2 — Containers

```mermaid
C4Container
    title Containers - Football Reliability Screener and Probability Bot

    Person(divine, "Divine", "Sole user")
    System_Ext(tg, "Telegram Bot API", "Interface")
    System_Ext(fdorg, "football-data.org", "Fixtures and results")
    System_Ext(fduk, "football-data.co.uk", "CSV history and shots")

    System_Boundary(sys, "Private GitHub repository - zero cost") {
        Container(worker, "Bot Worker", "TypeScript, Cloudflare Worker, Zod, plain fetch", "Webhook, auth, intake, forecast lookup, reply, prediction log, watchdog cron")
        ContainerDb(d1, "D1 database", "Cloudflare D1 (SQLite)", "matches, model runs and params, team form, predictions, omissions, uploads, events")
        Container(fit, "Nightly Fit Job", "Python 3, numpy, scipy, matplotlib, GitHub Actions", "Ingest, reconcile, score, refit three models, compute forecasts, publish run, weekly report, alerts")
        Container(cicd, "CI/CD", "GitHub Actions, Wrangler", "Tests, migrations, deploy, post-deploy smoke")
    }

    Rel(divine, tg, "Uploads file, reads replies", "HTTPS")
    Rel(tg, worker, "Webhook with secret-token header", "HTTPS")
    Rel(worker, tg, "sendMessage, getFile", "HTTPS")
    Rel(worker, d1, "Reads forecasts, writes predictions", "D1 binding")
    Rel(fit, d1, "Reads training data, writes runs and results", "D1 REST API, D1-scoped token")
    Rel(fit, fdorg, "Fixtures and results", "HTTPS, 10 req/min")
    Rel(divine, fduk, "Downloads CSV files by hand, loads them locally with footy load-csv", "browser, CLI")
    Rel(fit, tg, "Failure alerts, weekly report", "HTTPS")
    Rel(cicd, worker, "wrangler deploy", "Deploy token")
    Rel(cicd, d1, "Migrations", "Deploy token")
```

### 7.3 C4 Level 3 — Bot Worker components

```mermaid
C4Component
    title Components - Bot Worker

    Container_Ext(tg, "Telegram Bot API", "Webhook and API")
    ContainerDb_Ext(d1, "D1 database", "SQLite")

    Container_Boundary(worker, "Bot Worker (TypeScript)") {
        Component(entry, "Entry", "fetch and scheduled handlers", "Routes POST /tg/secret, cron to watchdog, everything else 404")
        Component(auth, "auth", "module", "verifyWebhook, checkSession. Only module that reads secrets and allowlist")
        Component(intake, "intake", "hand validator, Zod contract v1", "Size cap, UTF-8, JSON parse, schema validation, business checks")
        Component(dedupe, "update dedupe", "via repo", "Insert update_id once; ignore replays")
        Component(lookup, "forecast lookup", "via repo", "One batched read of the stored forecasts for the upload date; NO_FORECAST when absent")
        Component(upload, "upload pipeline", "orchestration", "Intake, team resolution, business checks, forecast lookup, immutable insert, then reply")
        Component(format, "format", "pure functions", "Render replies, split at 3,900 characters")
        Component(tgm, "telegram", "grammY api and fetch", "send, getFile, download, 429 handling")
        Component(repo, "repo", "D1 data-access layer", "Only module that issues SQL. Batched reads and writes")
        Component(watch, "watchdog", "cron handler", "Alert if active run is stale or missing")
        Component(cmds, "commands [v3]", "parser, registry, handlers", "Read-only: parse a / command, read stored rows, render, reply")
    }

    Rel(tg, entry, "POST update")
    Rel(entry, auth, "verify, then checkSession")
    Rel(entry, dedupe, "first time only")
    Rel(entry, intake, "document updates")
    Rel(entry, upload, "document updates")
    Rel(upload, lookup, "forecast per match")
    Rel(entry, format, "results")
    Rel(entry, tgm, "replies")
    Rel(tgm, tg, "HTTPS")
    Rel(entry, repo, "load run, log predictions")
    Rel(dedupe, repo, "uses")
    Rel(watch, repo, "reads active run")
    Rel(watch, tgm, "alert")
    Rel(entry, cmds, "text starting with /")
    Rel(cmds, repo, "read-only queries")
    Rel(cmds, watch, "collectFindings for /status")
    Rel(cmds, format, "render")
    Rel(cmds, tgm, "replies")
    Rel(repo, d1, "SQL")
```

### 7.4 C4 Level 3 — Fit job components

```mermaid
C4Component
    title Components - Nightly Fit Job

    ContainerDb_Ext(d1, "D1 database", "SQLite via REST")
    Container_Ext(src, "football-data.org (nightly) and hand-loaded co.uk CSV files", "HTTPS and local files")
    Container_Ext(tg, "Telegram Bot API", "HTTPS")

    Container_Boundary(fit, "Fit Job (Python, apps/fit)") {
        Component(cli, "cli", "Typer or argparse", "footy ingest, score, fit, publish, report, backtest")
        Component(ingest, "ingest", "clients and parsers", "football-data.org client, local co.uk CSV loader (footy load-csv), rate limiter")
        Component(alias, "aliases", "normaliser and resolver", "Source spelling to team_id; unmapped team reporting")
        Component(recon, "reconcile", "merge logic", "Merge two sources into matches; 90-minute result basis; anomaly detection")
        Component(models, "models", "numpy and scipy", "dixon_coles, pi_rating, bivariate_poisson, grid builders")
        Component(ens, "ensemble", "pure functions", "Rolling RPS to weights with shrinkage")
        Component(scoring, "scoring", "pure functions", "RPS, log loss, Brier, baseline frequencies, calibration bins")
        Component(form, "form", "pure functions", "team_form: season vs last-10 goals")
        Component(drift, "drift", "pure functions", "History rule and goals drift verdict per fixture")
        Component(fc, "forecast", "pure functions + repo", "Per-fixture grids, ensemble pool, markets, verdict, baseline")
        Component(pub, "publish", "sanity checks and switch", "Promotion gate, atomic active_run update, pruning")
        Component(rep, "report", "text and matplotlib", "Weekly calibration summary and chart")
        Component(repo, "repo", "D1 REST client", "Only module that issues SQL; retries and backoff")
        Component(alert, "alerts", "Telegram client", "Failure alerts with dedupe")
    }

    Rel(cli, ingest, "runs")
    Rel(ingest, src, "HTTPS")
    Rel(ingest, alias, "resolve names")
    Rel(ingest, recon, "raw rows")
    Rel(recon, repo, "upsert matches")
    Rel(cli, scoring, "score predictions")
    Rel(cli, models, "fit")
    Rel(models, ens, "per-model RPS history")
    Rel(cli, form, "snapshot form")
    Rel(cli, fc, "forecast fixtures")
    Rel(fc, drift, "verdict")
    Rel(cli, pub, "promote run")
    Rel(cli, rep, "weekly")
    Rel(pub, repo, "write run and params")
    Rel(rep, alert, "send")
    Rel(repo, d1, "REST")
    Rel(alert, tg, "HTTPS")
```

### 7.5 Deployment view

```mermaid
flowchart LR
    subgraph GH["GitHub (private repo, Free plan)"]
        REPO["Repository: main + short-lived feature branches"]
        CI["ci.yml (on pull request)"]
        DEP["deploy.yml (on push to main, environment: production)"]
        NIGHT["nightly.yml (cron 17 1 * * * + manual)"]
        BT["backtest.yml (monthly + manual)"]
    end
    subgraph CF["Cloudflare (Free plan)"]
        W["Worker: bot + cron watchdog"]
        D1[("D1 database")]
    end
    TG["Telegram Bot API"]
    DIV(["Divine"])
    SRC["football-data.org"]

    REPO --> CI
    REPO -->|merge| DEP
    DEP -->|"migrations, deploy (deploy token)"| W
    DEP -->|migrations| D1
    NIGHT -->|"D1 REST (D1-only token)"| D1
    NIGHT --> SRC
    NIGHT -->|alerts, weekly report| TG
    BT -->|read-only queries| D1
    DIV -->|upload .json| TG
    TG -->|webhook| W
    W --> D1
    W -->|replies| TG
```

### 7.6 Project structure (single private repository)

```
/                                  repo root
├── claude.md                      coding-agent guardrail (read order, drift checks, 12 rules)
├── prd/                           PRD_N.md (versioned, immutable snapshots)
├── system_architecture/           system_architecture_N.md (versioned, immutable snapshots)
├── essentials/                    system_architecture_essential_N.md (per build phase)
├── tracker/                       written by Claude Code during implementation (dated entries)
├── apps/
│   ├── bot/                       Cloudflare Worker (TypeScript)
│   │   ├── src/
│   │   │   ├── index.ts           fetch + scheduled entry points only
│   │   │   ├── auth/              verifyWebhook, checkSession
│   │   │   ├── intake/            Zod schema v1, size/UTF-8/JSON guards, business checks
│   │   │   ├── upload/            [v2] upload pipeline: intake, team resolution, forecast lookup, insert, reply
│   │   │   ├── (engine/ and drift/ are not built in v2: ADR-042, ADR-044)
│   │   │   ├── format/            reply rendering + splitting
│   │   │   ├── telegram/          send/getFile/download over plain fetch, 429 handling (ADR-043)
│   │   │   ├── repo/              D1 data-access layer (only SQL in the Worker)
│   │   │   ├── watchdog/          cron staleness check
│   │   │   ├── commands/          [v3] command parser, registry, handlers (read-only)
│   │   │   └── config/            constants, error catalogue
│   │   ├── test/                  Vitest (Workers pool): unit, repo-on-local-D1, e2e-with-fakes
│   │   └── wrangler.toml
│   └── fit/                       Python package `footy`
│       ├── src/footy/
│       │   ├── cli.py
│       │   ├── ingest/            fd_org client, fd_uk csv, rate limiter
│       │   ├── aliases/           normaliser, resolver
│       │   ├── reconcile/         merge, 90-minute basis, anomalies
│       │   ├── models/            dixon_coles.py, pi_rating.py, bivariate_poisson.py, grid.py
│       │   ├── ensemble/
│       │   ├── scoring/           rps, logloss, baselines, calibration
│       │   ├── form/
│       │   ├── drift.py, forecast/   [v2] drift verdict and per-fixture forecasts
│       │   ├── score/             [v2] settle pending predictions
│       │   ├── publish/
│       │   ├── report/
│       │   ├── alerts/
│       │   └── repo/              d1_client.py (only SQL in Python)
│       └── tests/                 pytest: unit, property, golden vectors, synthetic backtest
├── packages/
│   └── contracts/                 screener_v1.schema.json, golden fixtures, golden grid vectors; [v3] bot_commands.json, golden/normalise.json
├── data/
│   ├── canonical_teams.json       canonical names per competition (from PRD_1 §12)
│   ├── historical_teams.json      history-only (inactive) clubs for the 3-year window [Rev-1]
│   └── aliases/                   fd_org.json, fd_uk.json, screener.json (our own mapping files)
├── db/
│   └── migrations/                0001_*.sql ... (additive-first, never edited after merge)
├── scripts/                       set-webhook, smoke checks
├── docs/legal/                    source_terms_register.md (§9.8)
└── .github/workflows/             ci.yml, deploy.yml, data.yml [Rev-3], nightly.yml, backtest.yml
```

**[Rev-4]** As built, the fit package also has `backtest/` (walk-forward, report, job), `models/{structure,registry,types,golden}.py`, `fitting.py` (the `fit` job), `repo/{training,models}.py`, `jobs.py` (job result and `job_runs` bookkeeping), `clock.py`, `payload.py` (the payload text and hash shared by fit and the gate), `models/pooled.py` (what dc and bp share: team table, payload, optimiser) and `ensemble/weights.py`; `scoring/` holds the baseline and the calibration bins. The Worker's `repo/index.ts` gained `runs.readActive()`, `runs.readPointer()`, `runs.readActiveVerified()` (the payloads are fetched and hashed only when the pointer changes) and `payloadVerifies()`.
**[v2]** The Worker also has `intake/` (Zod schema, strict decode), `format/` (reply rendering and splitting), `upload/` (orchestration), `telegram/client.ts`, and `packages/contracts/screener_v1.schema.json` generated from the Zod schema. The fit package gains `drift.py`, `forecast/`, `score/`, `report/`, `telegram.py`, `ensemble/history.py` and the repos `forecasts.py`, `predictions.py`, `calibration.py`.

Rules: no raw source data (CSV, API dumps) is ever committed — tests use synthetic generators (ADR-025); secrets only in GitHub/Cloudflare secret stores; the bot imports nothing from `apps/fit` and vice versa; the only shared artifacts are `packages/contracts`, `data/`, and `db/migrations`.

### 7.7 "Frontend / backend flow"

There is no frontend. **Telegram is the UI**; the flow from Divine's point of view is a three-step ritual:

1. 08:00 IST — "run today" in the Claude Project → receives `screener_YYYY-MM-DD.json`.
2. Upload that file to the bot chat as a document.
3. Read the reply messages (probabilities, omissions, footer with model run and warnings).
4. [v3] At any time: send a command (for example `/status` before the upload, `/fixtures` to see which matches have a stored forecast) and read the reply. Commands change nothing.

Backend flow: Telegram → Worker (auth → dedupe → intake → resolve teams → read stored forecasts → log → render) → Telegram. Nothing else is user-facing; alerts and the weekly report arrive as ordinary Telegram messages from the same bot.

### 7.8 Authentication flow

```mermaid
sequenceDiagram
    autonumber
    participant T as Telegram
    participant W as Worker entry
    participant A as auth module
    participant R as repo (D1)
    T->>W: POST /tg/PATH_SECRET + secret-token header + update
    W->>W: path matches PATH_SECRET? else 404
    W->>A: verifyWebhook(request)
    A-->>W: header constant-time equal? else 401
    W->>A: checkSession(update)
    alt private chat AND chat.id = ALLOWED_CHAT_ID AND from.id = ALLOWED_USER_ID
        A-->>W: Session ok
        W->>R: markProcessed(update_id)
        alt first time
            R-->>W: firstTime = true
            W-->>T: 200 (immediately)
            W->>W: continue in waitUntil
        else replay
            R-->>W: firstTime = false
            W-->>T: 200 (no work)
        end
    else anyone else
        A-->>W: null
        W-->>T: 200, no reply (counter event only)
    end
```

Three independent layers, in order: unguessable path → Telegram secret-token header → chat-and-user allowlist. All three live behind `auth` (locked extensibility rule); swapping the scheme touches one module.

### 7.9 Data flow — nightly (01:17 UTC)

```mermaid
sequenceDiagram
    autonumber
    participant GH as GitHub Actions (nightly.yml)
    participant F as footy CLI
    participant S as football-data.org
    participant D as D1 (REST)
    participant T as Telegram
    GH->>F: footy ingest
    F->>S: matches window (paced)
    S-->>F: JSON
    F->>F: resolve aliases, reconcile, 90-minute basis
    F->>D: upsert matches, log fetches, record unmapped teams
    GH->>F: footy score
    F->>D: pending predictions with finished matches
    F->>D: write results, void postponed/cancelled
    GH->>F: footy fit
    F->>D: read training window and scored predictions
    F->>F: fit dc / pi / bp, weights, baselines, team_form, sanity checks
    F->>F: [v2] forecast every scheduled fixture in the next days (grids, pool, markets, history and drift verdict)
    F->>D: insert run (building) + params + form + forecasts
    GH->>F: footy publish
    F->>F: promotion gate passes?
    alt passes
        F->>D: UPDATE active_run (atomic), old run superseded, prune
    else fails
        F->>D: mark run rejected
        F->>T: alert (previous run stays active)
    end
    opt Monday
        GH->>F: footy report
        F->>T: weekly calibration message + chart
    end
    opt any step failed
        GH->>T: failure alert (if: failure())
    end
```

### 7.10 Data flow — morning upload

```mermaid
sequenceDiagram
    autonumber
    participant U as Divine
    participant T as Telegram
    participant W as Worker
    participant D as D1
    U->>T: upload screener.json
    T->>W: webhook update (authenticated, deduped)
    W-->>T: 200
    W->>D: insert uploads row (status received) [Rev-1]
    W->>T: getFile, download (size-capped)
    W->>W: parse + Zod v1 + business checks
    W->>D: [v2] ONE consistent read through the active_run pointer: run metadata, stored forecasts for the upload date, existing predictions for that date, team ids
    W->>W: per match: business checks, forecast lookup (NO_FORECAST or the stored verdict), copy the numbers
    W->>D: batch write: predictions (insert-or-ignore, first one wins), omissions, upload row finalised; then read back the stored rows to render
    W->>T: sendMessage x N (split)
    T-->>U: probabilities, omissions, footer
```

Order matters: **persist, then reply.** A reply never exists without its log row; if sending fails after persisting, a re-upload is answered from the log with identical numbers.

### 7.11 State machines

```mermaid
stateDiagram-v2
    direction LR
    [*] --> pending: published (insert)
    pending --> scored: match FINISHED with verified 90-minute score
    pending --> void: POSTPONED / CANCELLED / SUSPENDED / AWARDED / unverified result / NO_RESULT after 3 days
    scored --> [*]
    void --> [*]
```

```mermaid
stateDiagram-v2
    direction LR
    [*] --> building: fit job inserts run
    building --> failed: all three models failed or job error
    building --> rejected: promotion gate failed
    building --> active: gate passed, active_run switched
    active --> superseded: next run promoted
    superseded --> active: manual rollback (switch pointer back)
    failed --> [*]
    rejected --> [*]
```


### 7.12 Data flow — a command [v3]

```mermaid
sequenceDiagram
    autonumber
    participant U as Divine
    participant T as Telegram
    participant W as Worker
    participant D as D1
    U->>T: /status (any command)
    T->>W: webhook update (path, header, allowlist, update_id dedupe as in §7.8)
    W-->>T: 200
    W->>W: parseCommand (pure): known command? arguments valid?
    W->>D: one or two read-only batches through QueryRepository
    W->>W: render (pure), split at 3,900 characters
    W->>T: sendMessage x N (N at most 5)
    T-->>U: reply
```

Nothing is written on this path except the `processed_updates` row (kind `command`) and, on an unexpected failure, one `command_failed` event. A replayed update does no work (§9.6).

---

## 8. Critical components — deep dive (design phase 7)

### 8.1 Grid engine and markets

**One grid per match.** Home goals i and away goals j, 0 ≤ i, j ≤ 12 (13×13 = 169 cells). Each model produces a grid; the ensemble is the **weighted linear pool** of the available grids, `G = Σ w_m · G_m` with `Σ w_m = 1`, so `ΣG = 1` automatically. Every market is derived from `G`:

- P(home) = Σ_{i>j} G, P(draw) = Σ_{i=j} G, P(away) = Σ_{i<j} G.
- P(over L) for L ∈ {0.5,…,5.5} = Σ_{i+j > L} G; Under = 1 − Over (computed, never stored separately).
- Total-goals pmf (0..11, 12+) is derived once and used for RPS on totals.

Properties (property-tested in Python; [v2] the Worker has no grid code): grid ≥ 0, sums to 1 within 1e-9, tail mass beyond 12 goals < 1e-6 before renormalisation **[Rev-4: measured to hold per side up to about 2.3 goals; above that the grid is still renormalised and still sums to 1]**, overs monotone non-increasing in L, mirror symmetry when home/away parameters are swapped with home-advantage removed.

Cross-language parity: [v2] there is no second implementation. Python is the only grid engine (ADR-042); the Worker stores and shows numbers computed by it. `packages/contracts/golden/` keeps its vectors as regression tests for the Python code, and the 1e-9 TypeScript comparison of version 1 is no longer required. The stored numbers are held to the same properties by database CHECK constraints (§5.5) and the forecast tests.

**[Rev-4] Extreme-fixture guard (ADR-039).** When a grid is built from fitted parameters, each goal rate is clipped to 0.01..6 and the Dixon-Coles rho is clamped to the interval in which every correction factor stays positive (from -0.999 / max(lambda, 1) to min(0.999, 0.999 / (lambda_home x lambda_away))). Inside the normal range this changes nothing; for a very strong side against a very weak one it prevents a negative factor (which crashed a test backtest). The golden vectors include clipped and clamped cases, so any other implementation must apply the same rule. The bivariate Poisson shared-covariance rate is floored separately at 1e-4, which is below the fit's own lower bound (about 0.0003), so a fitted covariance is never altered.

### 8.2 Models (all implemented in-house with numpy/scipy; `penaltyblog` is an optional test oracle, not a runtime dependency — ADR-019)

| Model | What it estimates | Grid construction | Stored payload |
|---|---|---|---|
| **Dixon-Coles (dc)** | Per-team attack/defence, home advantage, league offsets, low-score correction ρ, with exponential time-decay weights | Independent Poisson with the Dixon-Coles τ adjustment on (0,0),(0,1),(1,0),(1,1), renormalised | team parameters, league offsets, ρ, home advantage, decay ξ |
| **Pi-rating (pi)** | Per-team home and away ratings updated chronologically from score discrepancies (Constantinou & Fenton, 2013; formulas and constants are taken from the paper at build time and unit-tested against hand-computed examples) | Rating difference → expected goal difference d; with league total-goals level T: λ_home = max(ε, (T+d)/2), λ_away = max(ε, (T−d)/2); independent-Poisson grid. **Hypothesis** (ADR-006) | ratings, per-league T, mapping constants |
| **Bivariate Poisson (bp)** | Per-team attack/defence plus a shared covariance term λ3 | Karlis–Ntzoufras bivariate Poisson pmf: P(i,j) = e^{−(λ1+λ2+λ3)} · λ1^i/i! · λ2^j/j! · Σ_{k≤min(i,j)} C(i,k)C(j,k)k!(λ3/(λ1λ2))^k | team parameters, λ3, home advantage |

Cross-league handling (ADR-007, **hypothesis**): the three models fit on one pooled match set. Leagues are only weakly connected (Champions League matches, plus promoted/relegated clubs moving between divisions in the window), so team parameters are **shrunk toward their league mean** and league offsets are identified through those links. UCL replies carry a note that cross-league strength is the weakest-identified quantity. The walk-forward backtest reports per-competition RPS so a competition where this fails is visible rather than hidden.

Time decay: weight of a match = `exp(−ξ·age_days)`; initial half-life 300 days (a starting value tuned in the backtest, **unvalidated**).

Failure semantics (ADR-019/FR-07): a model that fails convergence or sanity checks tonight is stored with `status='failed'`, **not** silently replaced by yesterday's parameters; the bot runs the others and prints "model X unavailable".

Sanity checks per model before storing `ok`: optimiser success, finite parameters, all |attack/defence| within bounds, mean λ per league in [0.3, 3.5], a test grid for a typical fixture sums to 1.

**[Rev-4] As built (Stages 3 and 4).** (a) Dixon-Coles and bivariate Poisson share one pooled parameterisation: intercept, home advantage, league offsets and team deviations shrunk toward their league mean by a ridge (`shrink_team` 4, `shrink_league` 0.1, unvalidated); fitted with L-BFGS-B and an analytic gradient, at most 3000 iterations, tolerance 1e-10 (the first values, 500 and 1e-12, failed on real data in a few folds), no warm start (a cold fit takes about 1 s for Dixon-Coles and about 8 s for bivariate Poisson on a production-sized set). A fit with fewer than 50 matches in the window fails. (b) The bivariate Poisson gradient uses dP(x,y)/dlambda1 = P(x-1,y) - P(x,y) (likewise lambda2; lambda3 with P(x-1,y-1)); lambda3 is one shared constant. (c) Pi-rating constants were verified against the paper (verify-at-build item 8): lambda 0.035, gamma 0.7, b 10, c 3, psi(e) = 3 log10(1+e), initial rating 0. The grid mapping adds one fitted scale s (observed on predicted goal difference, through the origin, clipped to 0.2..2), so d = s x gD before the T +/- d split. The pi-rating is league-agnostic and has no shrinkage. (d) The training window and the time decay end at the data cut-off (the latest stored verified result) or at `--as-of`.

### 8.3 Ensemble weighting (ADR-020)

For each model m let `RPS̄_m` be its mean RPS (1X2) over the most recent N = 200 scored predictions that have a stored per-model probability. Raw weight `w̃_m = exp(−κ · RPS̄_m)`, normalised to `w_rps`. With `n` scored predictions available, final weight `w = (n/(n+50))·w_rps + (50/(n+50))·(1/M)` over the M models that fit tonight. Until the first scored predictions exist, **initial weights come from the walk-forward backtest** (run at launch) and equal weights if that is unavailable. κ is a backtest-tuned starting value, **unvalidated**. Weights are written into `model_runs.ensemble_json` and copied into every prediction (`weights_json`).

**[Rev-4] As built (ADR-040).** `w = n/(n+50) x w_rps + 50/(n+50) x w_prior`, where `w_prior` is the softmax of the walk-forward backtest's mean RPS when a stored `backtest` summary covers every fitted model, and equal weights otherwise (the rule written above). kappa = 100, because RPS differences between the models are about 0.001 to 0.01. All are starting values, unvalidated. The prior is used only when the stored backtest summary was produced with the same half-life and shrinkage as the run and rests on at least 200 forecasts per model; the backtest's reported result is the sweep cell with the production settings. In the production backtest the three models' RPS were within 0.0034 of each other, so the weights stay near equal.

### 8.4 Drift filter (ADR-021)

> **[Rev-1, ADR-026] v1 ships goals-only drift.** The shots check, the 8-of-10 shots coverage rule and the shots columns of `team_form` are deferred until amendment A-1 (football-data.co.uk) is decided. The shots text below is the specification for that later, additive change. Replies say `Drift: stable (goals only)`.

> **[v2, ADR-044]** The history rule and the drift check are evaluated in Python when the forecast is made (`footy/drift.py`), from the run's own `team_form`. The result is stored with the forecast: verdict `ok`, `INSUFFICIENT_HISTORY` or `DRIFT`, and the statistics in `detail_json`. A team with no `team_form` row, no match in the current season (its season average is undefined) or an unavailable mean counts as `INSUFFICIENT_HISTORY`. The comparison uses a tolerance of 1e-9 so a difference of exactly the threshold passes. When both teams fail, `INSUFFICIENT_HISTORY` takes precedence over `DRIFT`.

Inputs per team from `team_form` (precomputed at fit time): season goals for/against per match, last-10 goals for/against, and shots where coverage allows.

- `Δgf = |l10_gf − season_gf|`, `Δga = |l10_ga − season_ga|`.
- Goals check passes if `max(Δgf, Δga) ≤ θ_goals` (starting value **0.6 goals per match**, unvalidated: with ≈ 1.2 SD of goals per match, a 10-match mean has SE ≈ 0.38, so 0.6 ≈ 1.6 SE).
- Shots check (only if ≥ 8 of the last 10 matches have shots): relative shift `|l10_sf − season_sf|/season_sf` and the defensive counterpart ≤ `θ_shots` (starting value **25%**, unvalidated).
- A team is stable if every available check passes; a match is stable only if **both** teams are. The verdict and numbers go to `drift_json` and the omission reason lists which check failed.
- A team with `n_training < 10` is omitted as `INSUFFICIENT_HISTORY` before drift runs; a team with `l10_n < 10` is also `INSUFFICIENT_HISTORY` (drift cannot be evaluated).
- Thresholds live in `model_runs.config_json` so every prediction is reproducible and threshold changes are code-reviewed through the fit job, not edited ad hoc. Every reply footer says "drift thresholds: starting values, unvalidated" until a backtest marks them validated.

### 8.5 Ingestion, reconciliation and aliases

- **Sources and gating:** each source is behind `SOURCE_ENABLED_<NAME>` configuration, default **off** until the legal register entry (§9.8) is signed off. [Rev-1, ADR-032] The terms and free-history-depth checks are done as notes during Stage 1, before any ingestion code exists.
- **Fetch plan (nightly):** football-data.org — one request per competition (`PL, PD, BL1, SA, FL1, DED, PPL, ELC, CL`) for `dateFrom = today−7`, `dateTo = today+3`, spaced ≥ 6.5 s apart (≈ 60 s total, within 10/min). football-data.co.uk is **never fetched automatically** [Rev-2, ADR-035]: its CSV files are downloaded by hand and loaded with `footy load-csv`.
- **Alias resolution:** every source team name is normalised and looked up in `team_aliases (source, alias_norm)`. Unknown → the match is skipped for training, an `events` row is written, and one deduped alert lists the unmapped names. Nothing is guessed. [Rev-1, ADR-027] Clubs that left the ten competitions during the window are listed in `data/historical_teams.json` (inactive rows with per-source aliases) so their matches are kept.
- **Reconciliation:** the same match from two sources is joined on `(comp, season, home_team_id, away_team_id)` with a ±1 day date tolerance (SPL plays pairs several times per season, so the date tolerance matters there). Goals preference: football-data.org `score.regularTime` → `score.fullTime` when `duration=REGULAR` → co.uk `FTHG/FTAG`. If both sources have a score and disagree, the job keeps the football-data.org value, writes an `events` anomaly and fails the run with exit code `2` if more than 3 disagree (a signal of a parsing or mapping bug).
- **[Rev-3] Under A-1 path 2 there is one source**, so the two-source join and the co.uk preference are not built. The disagreement rule is applied to a stored verified result that the source later reports differently: those rows are not written, an `anomaly_result_changed` event is recorded, and more than 3 in one run fails the run (exit code 2) and writes nothing. The free plan was seen to report a few finished matches as `TIMED` again; the forward-only status rule keeps the stored result and records a deduped `anomaly_status_regression` event. `fullTime` in football-data.org includes extra time and the shootout; only `regularTime` (or `fullTime` when `duration=REGULAR`) is a 90-minute score (checked against the v4 documentation).
- **Result validity:** goals in 0..20; status transitions only forward; a `FINISHED` match with non-REGULAR duration and no `regularTime` → `result_basis='unverified'`.
- **Freshness:** per competition, `max(match_date)` of finished matches is recorded in the run's `diagnostics_json`; `team_form.latest_match_date` lets the bot add "SPL data through <date>" notes (GR-17).
- **Season rollover:** a competition's team list is compared with football-data.org's team list for that competition each night; a team in the source but not in `teams` raises a deduped alert ("canonical list needs a summer update").

### 8.6 Run publishing and the promotion gate

1. The fit job inserts `model_runs(status='building')`, then `model_params` and `team_form` rows with that `run_id`.
2. **Promotion gate** [Rev-1, ADR-030]: structural checks (at least one model `ok`; `team_form` covers ≥ 95% of active teams; all payload hashes verify on re-read; row counts plausible) plus a **stability guard**: no team's attack or defence value moves by more than a bound (stored in `config_json`, labelled unvalidated) versus the active run. A performance comparison against the active run is **not** built in v1: the new run's training window contains the most recent days, so such a comparison would be in-sample. Out-of-sample evidence comes from scored predictions and the weekly report.
3. Pass → one statement updates the pointer: `UPDATE active_run SET run_id=?, activated_at=? WHERE id=1`, then the previous run becomes `superseded`. Fail → new run is `rejected`; the old run stays active; alert.
4. The Worker reads the run with **one statement keyed through the pointer** (`WHERE run_id = (SELECT run_id FROM active_run WHERE id = 1)`), so it never sees a half-published run.
5. Rollback = set the pointer back to a `superseded` run still retained (30 runs kept).

**[Rev-4] As built.** `footy fit` stores a `building` run with a row for every attempted model (a failed model as `failed` with its reason and no payload) and a `team_form` row for every active team. The gate checks: status `building`; every attempted model has a row and at least one is `ok`; `team_form` covers at least 95% of active teams; every `ok` payload's SHA-256 verifies on re-read and its version is understood; each payload holds at least 95% of the teams that had training matches; and the stability guard (bound **0.5** on any team value: attack or defence for dc and bp, home or away rating for pi; stored in `config_json`, unvalidated; skipped when there is no active run). A rejected run becomes `rejected`, the reasons are stored in its `diagnostics_json`, an `alert` event is written (deduped per run; the Telegram sender is Stage 7) and the command exits with code 4. Promotion is one batch of three guarded statements (activate the run; upsert the pointer only if that run is active; supersede the old run only if the pointer moved); promoting the active run again is a no-op. Runs beyond the newest 30, never the active one, are deleted with their children. Rollback: `footy publish --rollback RUN_ID` (a `superseded` run, no gate). The run must record `n_teams_training` (a run that omits it is rejected, so the payload-coverage check cannot be skipped by leaving the number out); the active run's payloads must verify before the stability guard compares with them (otherwise the guard is skipped for that model and the reason is recorded). `footy publish --run-id RUN_ID --accept-drift` skips ONLY the stability guard for that one run, after a human decided a large move is real (a data correction, a league re-link); it writes an `info` event `drift_accepted`, the other checks still apply, and it is refused without an explicit run id. Without it a legitimate large move would reject every later run, because each is compared with the same active run.

**[v2] Forecast checks in the gate (ADR-042).** `footy fit` records `diagnostics_json.n_forecast_fixtures` (fixtures forecast) and writes that many rows; the gate rejects a run that did not record the number or whose `fixture_forecasts` rows number fewer than recorded (a run with zero fixtures in the window passes). Because promotion switches one pointer, the forecasts and the parameters go live together and roll back together. After a successful promotion, forecasts outside the newest 5 servable runs (`active`, `superseded`, `building`) are deleted, as are those of rejected and failed runs (the active run's are never deleted); a rollback to a run whose forecasts were pruned succeeds but is reported with a warning, because every match would then be `NO_FORECAST`.

**[v2] Forecast carry-over (code review of PR 21).** A fit that found no upcoming fixtures (ingest not yet run, a feed gap) records `n_forecast_fixtures = 0`, which passes the count check; promoting it would silence the bot for the days the active run still serves. The gate therefore also requires the new run to have forecast at least 50% (`GATE_FORECAST_CARRYOVER`, unvalidated) of the fixtures the active run forecast for the new run's start date or later; fixtures already played do not count, and there is nothing to compare when no run is active. Like the stability guard it is skipped by the explicit `--accept-drift` override and recorded in `checks.forecast_carryover`.

### 8.7 Prediction log and scoring

- `fixture_key = "<kickoff UTC date>|<comp>|<home_team_id>|<away_team_id>"`. Insert uses `INSERT OR IGNORE`; if a row exists it is returned unchanged. This makes concurrent or repeated uploads safe (NFR-06) and prevents later-information bias.
- A prediction is only created if `kickoff_utc > now` and `≤ now + 48 h`.
- [v2] The Worker creates a prediction by **copying** the stored forecast row (`verdict='ok'`) for the fixture into `predictions` with `INSERT ... ON CONFLICT (fixture_key) DO NOTHING`: only a clash on the fixture key is ignored, while a row that breaks a CHECK or NOT NULL constraint raises and rolls the whole batch back, leaving the upload `received`; the probabilities, per-model markets, weights, drift statistics and the league baseline. It computes nothing. Two simultaneous uploads give one row per fixture because of the unique key; the reply is rendered from the rows read back after the insert, so it shows what is stored. The row's `upload_id` marks which upload created it; a fixture created by an earlier upload is shown as "already logged".
- `footy score` matches pending predictions to finished `matches` by `fixture_key` components. Postponed/cancelled/suspended/awarded → `void`. [Rev-1, ADR-028] A `pending` prediction with no matching finished match 3 days after kickoff (for example a rescheduled match, whose new kickoff date no longer matches the key) → `void` with `void_reason='NO_RESULT'`, listed in one deduped alert. Scored columns: 1X2 RPS, totals RPS (ordered categories 0,1,…,11,12+), 1X2 log loss. Binary over/under Brier scores are computed on read from the stored over probabilities.
- [v2] Scoring detail: a pending prediction is joined to `matches` on `(match_date, comp_code, home_team_id, away_team_id)`. `FINISHED` with a verified 90-minute result → `scored` (RPS 1X2, RPS totals from `total_json`, log loss); `FINISHED` unverified → stays `pending` (the source can still add the 90-minute score, which reconcile allows) and becomes void `UNVERIFIED_RESULT` only once 3 days have passed since kickoff; `POSTPONED`, `CANCELLED`, `SUSPENDED`, `AWARDED` → void with that name; anything else (including no row, for example a rescheduled match) stays `pending` until 3 days after kickoff and then becomes void `NO_RESULT`. Every update is guarded by `status='pending'`, so re-running changes nothing.
- Baseline for the success metric: for each prediction, the league-average-frequency forecast (H/D/A frequencies and over frequencies per competition over the training window, snapshotted in `config_json`). **Success (PRD):** mean 1X2 RPS of the published ensemble is lower than the baseline's over ≥ 300 scored predictions. A paired bootstrap interval is reported alongside; it is information, not a claim of significance.
- [v2] The baseline for each prediction is the `baseline_json` copied into it from the forecast (the league-frequency forecast of the run that made the prediction), so the comparison stays valid after that run is pruned. The weekly report (`footy report`) gives, over all scored predictions: the ensemble's and the baseline's mean RPS (1X2 and totals), their paired difference with a 95% percentile-bootstrap interval (2,000 resamples, fixed seed; information, not a significance claim), per-model and per-competition RPS, calibration bins for the three 1X2 outcomes and each over line, the omission rate by reason (omitted and published are both counted per processed upload, so re-uploading an unchanged file does not move the rate), and the progress toward 300 scored predictions, with plain wording when the sample is small. Each report writes one `calibration_snapshots` row.

### 8.8 Reply rendering

Plain text, one block per match, UTC and IST kickoff times (IST = UTC+5:30, no daylight saving). [Rev-1] When the IST time falls on the next calendar day (kickoff after 18:30 UTC) the IST time carries `+1d`, for example `20:00 UTC (01:30 IST +1d)`:

```
EPL  Arsenal vs Chelsea   17 Oct 15:00 UTC (20:30 IST)
1X2   H 52.1%  D 24.3%  A 23.6%
Over  0.5 97.0 | 1.5 84.2 | 2.5 61.0 | 3.5 36.4 | 4.5 17.8 | 5.5 7.2   (Under = 100 - Over)
Models dc+pi+bp  w 0.41/0.33/0.26   Drift: stable (goals only)
```

Footer once per upload: run id and data cut-off, number published / omitted / excluded by screener (counted by reason), banners (STALE MODELS, model unavailable, SPL data-through note, UCL cross-league note, which also says the UCL final may be played at a neutral ground [Rev-1]), and "drift thresholds: starting values, unvalidated" until validated. Message splitting is at block boundaries so a match is never cut.

[v2] The footer also counts omissions by reason (including `NO_FORECAST`) and adds the banner "no forecasts stored for this run" when the run has no forecast rows. The reply shows team names from our own table, never free text from the file; a free-text field of the file (`notes`, player names, URLs) is not echoed at all. Screener exclusions are counted by their `G1` to `G6` code, anything else as `OTHER`.

### 8.9 Caching, queues and storage (design-phase checklist)

- **Caching:** none added. D1 is the cache of external data; the prediction log with unique `fixture_key` acts as the inference cache (a repeated fixture is served from the log). A separate cache layer would add a moving part with no benefit at ≈ 50 requests/day (ADR-023).
- **Queues:** none. The only asynchronous work is `waitUntil` after acknowledging the webhook, and the nightly batch. Cloudflare Queues stays a documented contingency only (availability on the Free plan not verified).
- **Storage:** D1 only; model blobs are rows, not files. Source CSVs are parsed in memory and never persisted to git or object storage.

### 8.10 CPU budget and the fallback ladder (ADR-013)

[v2] The table below is the version-1 estimate, kept for the record: the design it describes failed the gate (below). In version 2 the Worker does no grid, drift or ensemble arithmetic, so only the routing, JSON/Zod, glue and rendering rows remain; the Stage 5b gate re-measures them (hypothesis: well under 6 ms).

| Step | Estimate |
|---|---|
| Routing + auth + dedupe | < 1 ms |
| JSON parse + Zod (≈ 60 KB) | 1–2 ms |
| Parse model payload blobs (≈ 150 KB total) | 0.5–1 ms |
| 60 × 3 grids, 169 cells, bivariate Poisson sums | 1–2 ms |
| Linear pool, markets, rendering | 0.5 ms |
| grammY / fetch glue | 0.5–2 ms |
| **Total** | **≈ 4–8 ms vs 10 ms limit** |

**Measurement method [Rev-1]:** CPU time is read from the `cpuTime` field of the invocation log in Workers Logs (or a Tail Worker), not from in-Worker timers, which do not advance during compute. Local `wrangler dev` timings are indicative only; the gate uses production-like invocations.

Gate: if p95 over 20 production-like uploads exceeds **6 ms** (or any invocation hits the limit), move down the ladder:

- **F1 — Trim:** fetch parameters only for involved teams (per-team rows), skip Zod for the bulk arrays (hand validator), drop grammY features not needed, precompute bivariate-Poisson factorial tables.
- **F2 — Split across invocations:** process the file in chunks of N matches, each triggered by a self-request, tolerating the extra subrequests.
- **F3 — Offload to Actions:** the Worker only authenticates, stores the file and calls `workflow_dispatch`; Python computes grids with the reference code and replies. Eliminates duplicated TS maths and the CPU risk, at the cost of ≈ 20–60 s latency, a fine-grained GitHub token stored in the Worker, and about 1–2 Actions minutes per upload. This changes the PRD's "bot computes" design, so it is a **new architecture version** if triggered — it is not silently adopted.

[Rev-1] **Parked idea, not a decision (kept in the tracker):** the nightly job already holds the next 3 days of fixtures and could pre-compute and store each match's grid so the Worker only looks it up. That would replace F2/F3 and remove the TypeScript grid port, but it changes the PRD design, so it also needs an architecture version bump. Consider it only if the Stage 1 spike gives p95 above 6 ms.

**[Rev-3] Stage 1 gate outcome (production, Workers Logs, `docs/verification.md` section 2):** the design as built missed the gate (p95 22 ms, max 63 ms over 73 requests). F1 as specified above was applied (hand validator, per-team rows, Poisson recurrence) and re-measured: p50 3 ms, **p95 16 ms**, max 22 ms over 39 requests; the first requests on a fresh isolate cost 22, 13, 9, 4 and 12 ms. The gate is still not met, F1 is exhausted, and because uploads arrive about once a day nearly every real upload is a cold request. **Divine decided on 2026-10-16 to take the pre-computed-grids idea (ADR-037).** F2, F3 and the paid plan were not adopted. The redesign (where grids are stored and how large, how many days of fixtures, the missing-grid fallback, the first-prediction-immutable rule, Python as the only grid implementation) belongs to PRD_2 and a new architecture version made in design chat. Until then this version stays the build scope; Stages 2 to 4 and 6 do not depend on the Worker grid code, and Stages 5 and 7 wait for the new version.

**[v2] Resolution (ADR-042).** The pre-computed-grids direction is now a design: §8.11. F2, F3 and the Workers Paid plan remain unadopted. The Stage 5b gate (essentials 2) measures p95 on production-like uploads of 15, 60 and 100 matches against the 6 ms target; if it is still missed, the next steps are F1 trims of the remaining parse and validation work (hand validator instead of Zod), then escalation to Divine.

**[v2] F1 applied to the screener validation (ADR-047, 2026-10-18).** The first production measurement (verification section 7) gave 7 to 9 ms of CPU per warmed upload and 11 to 25 ms for the first request after a quiet period, against the 6 ms target, and the cost did not grow with the number of matches: it is fixed work. The runtime validation moved from Zod to a hand-written validator (`intake/validate.ts`), which also removes Zod from the Worker bundle. `intake/schema.ts` stays the single source of the contract (generated JSON Schema, drift test), and `test/intake-validate.test.ts` requires the same verdict, the same issue paths and codes, and the same parsed data as the Zod schema on thousands of mutated files. Re-measurement follows the merge (verification section 7).

**[v2] Outcome (ADR-048, 2026-10-18).** After the trim the warmed cost is 5 to 8 ms (p50 7) and the first request after a quiet period 14 to 17 ms, so the 6 ms target is not met. Divine accepted the miss and chose to proceed. F2, F3 and the paid plan stay unadopted; the paid plan is the fallback if uploads are ever cut off in production.

---

### 8.11 [v2] Nightly forecasts (ADR-042)

**What.** After `footy fit` has fitted the models, weighted the ensemble and snapshotted `team_form`, it computes one forecast row for every scheduled fixture in the forecast window and writes them with the run. The window is the UTC dates from today to today + 4 (`forecast.horizon_days = 4`, stored in `config_json`): the upload window is kickoff in (now, now + 48 h], and the extra days cover a nightly run that was late or failed. A fixture is a `matches` row with status `SCHEDULED` or `TIMED`.

**Per fixture** (pure code in `footy/forecast` and `footy/drift.py`):

1. `fixture_key` as in §8.7.
2. History and drift (§8.4) from the run's `team_form` → `ok`, `INSUFFICIENT_HISTORY` or `DRIFT`.
3. Each `ok` model that knows both teams builds its grid (§8.1 with the extreme-fixture guard). A model that cannot build the grid for this fixture is left out and named in `detail_json`. If no model remains, the verdict is `NO_MODEL`.
4. Weights are the run's ensemble weights over the models that produced a grid, renormalised (equal weights if they sum to 0). The ensemble grid is the linear pool; every market derives from that one grid. Per-model markets (1X2 and the 13-category total-goals pmf) are stored in `models_json`, so per-model RPS can be recomputed after the match (§8.3).
5. Only `ok` rows carry probabilities. The other rows carry the reason and statistics in `detail_json` so the Worker can say why.

**Why markets and not grids.** The Worker needs 1X2 and the six over lines. The overs and the totals RPS follow from the 13-category total-goals pmf, and the markets of a linear pool of grids equal the weighted sum of the models' markets, so nothing is lost. A row is about 2 KB against about 6 KB for a 169-cell grid, and the Worker never handles a grid.

**Size and lifecycle.** About 15–45 fixtures a day (§3.1) in a 5-day window is 75–225 rows, up to about 400 on a very full week: about 0.8 MB a run, about 400 rows written a night against the 100,000 daily limit. Rows are kept for the newest 5 servable runs (`active`, `superseded` for a rollback, `building` awaiting a publish) and deleted for older ones and for rejected or failed runs; the active run's are never deleted.

**Missing fixtures.** The window is built from `matches`, which the nightly ingest fills for today−7 to today+3. A fixture the screener lists that is not in the window (added or moved after the run, outside the ingest range, or from a competition the source does not cover) has no row: the Worker answers `NO_FORECAST`. Nothing is computed as a fallback (PRD_2 decision 28).

**First prediction immutable.** Forecasts of later nights never change a stored prediction (§8.7). A fixture re-uploaded the next day is answered from the log, not from the newer forecast.

**Staleness.** The active run's age drives the STALE MODELS banner (36 h); forecasts older than their run do not exist, so one age covers both.

### 8.12 [v3] Bot commands (ADR-049 to ADR-052)

**What.** Ten read-only commands (§6.10) let Divine see the stored state from the chat: health, upcoming verdicts, logged predictions and results, the weekly report, the last upload, a team's form and the recent alerts. They replace "open GitHub or wait for an alert" for everyday checks; they do not replace the screener upload, which stays the only way to get and log probabilities.

**Read-only by construction.**
1. The `commands` module receives a `QueryRepository` whose methods are `SELECT` statements only, the `EventRepository` (for `command_failed` only) and the `telegram` client. It does not import `upload/`, `intake/` or any writing repository method.
2. A test runs every command against a seeded local D1 and asserts that the row counts and contents of `predictions`, `omissions`, `uploads`, `fixture_forecasts`, `model_runs`, `active_run`, `team_form` and `calibration_snapshots` are unchanged (invariant 9, §5.7).
3. No command starts a job, switches a run or holds a token beyond the bot token (ADR-051).

**One rule, one place.**
- `/status` calls the watchdog's pure `collectFindings` instead of re-implementing its checks, so the chat and the cron cannot disagree.
- `/team` shows the stored fixture verdict and the raw `team_form` numbers; it does not judge drift itself (ADR-044).
- `/fixtures` shows the verdicts the nightly job stored; the Worker computes nothing (ADR-042) and shows no probability (ADR-050).
- `/report` shows the numbers of the stored snapshot; it computes no metric.
- The alert predicate and the name normaliser exist in both languages and are pinned by a repository check and by shared vectors (§6.10).

**Why verdicts only in `/fixtures` (ADR-050).** Showing a fixture's probabilities before the screener runs would skip gates G1 to G6, which is what makes the numbers worth reading, and the numbers would never be logged or scored, so the calibration record would no longer describe everything Divine saw. A verdict is enough to answer the practical question "will the upload be able to answer this match?".

**Rendering.** Plain text as in §8.8: competition codes, team names from our `teams` table, UTC and IST times, values from our own rows. Our own rows are still passed through `clean()` (control characters removed, length capped). Long replies are split at block or line boundaries, at most 5 messages; a longer list ends with "and N more".

**Failure handling.** An unexpected exception (a D1 error, a bug) replies "Internal error, id=<id>" once and writes a `command_failed` event (`level` `error`, detail: command name and error id, dedupe key per hour), and the request log line carries `E_INTERNAL`. Nothing needs undoing because nothing was written. A missing bot token records `bot_token_missing` as the usage hint does. `command_failed` is not part of the nightly health check: the failure was already shown to Divine.

**CPU.** A command does no download, no JSON parse of a file and no validation, so it is expected to cost less than an upload (warmed 5 to 8 ms after the F1 trim, ADR-048). The heaviest are `/team` (it normalises about 240 team names) and `/status` (several small reads in one batch). They are measured in Stage 8 from Workers Logs `cpuTime`; a command above 10 ms gets the F1 treatment (fewer rows read, simpler rendering). The worst case is a silent reply that Divine sends again; nothing is lost because nothing is written (risk R-P13).

## 9. Cross-cutting concerns (design phase 8)

### 9.1 Security

**Trust boundaries.** Untrusted: every inbound Telegram update, the uploaded JSON (it is produced by an LLM-driven screener from web pages — treat it as hostile input), every external CSV/JSON source. Trusted only after validation: our own D1 rows.

**Threat table** (IDs are referenced by tests and §15).

| ID | Threat | Control | Verified by |
|---|---|---|---|
| S1 | Spoofed webhook calls | Unguessable path `/tg/<WEBHOOK_PATH_SECRET>` + `X-Telegram-Bot-Api-Secret-Token` compared in constant time; any mismatch → 404/401 with no body | Vitest: wrong path, missing/wrong header |
| S2 | Another Telegram user/group messages the bot | `checkSession` requires private chat AND `chat.id = ALLOWED_CHAT_ID` AND `from.id = ALLOWED_USER_ID`; otherwise 200 with no reply (no oracle) | Vitest matrix |
| S3 | Update replay / Telegram retries | `processed_updates` insert-once on `update_id`; replay → 200, no work | Vitest |
| S4 | Oversized / malformed / hostile file | `document.file_size` pre-check, 256 KB cap re-checked on bytes, strict UTF-8 decode, `JSON.parse` in try/catch, Zod object schemas that strip unknown keys (§6.1) with string length caps [Rev-1] and array caps (≤ 100 matches), no URL in the file is ever fetched, no `eval`/dynamic code | Vitest fuzz-style cases |
| S5 | Instruction-like text inside JSON strings (prompt-injection residue) | There is **no LLM in the runtime path**; strings are data. Rendered text is built from validated enums/numbers plus team names resolved from our canonical table — free-text from the file (notes, URLs) is never echoed unescaped | Vitest: injection strings in every free-text field |
| S6 | Secret leakage via logs, errors or git | Logger redaction list; request bodies never logged; gitleaks in CI; `.gitignore` for `.env`, `.dev.vars` | CI secret scan |
| S7 | Over-privileged tokens | Nightly job uses a Cloudflare API token scoped to **D1 edit only** (ADR-018); deploy token separate and only referenced by `deploy.yml` | Token inventory below |
| S8 | Supply chain (npm, PyPI, Actions) | Lockfiles committed; versions pinned; third-party Actions pinned to commit SHA; Dependabot (or manual monthly) review; runtime dependency list kept minimal (Zod only in the Worker [v2, ADR-043: no grammY]; numpy, scipy, requests, matplotlib in the fit job) | CI `npm ci` / `pip install --require-hashes` where practical |
| S9 | Poisoned or broken source data | Range checks, anomaly rule in reconciliation, source disagreement fails the run, promotion gate (§8.6) keeps the previous run | pytest with corrupted fixtures |
| S10 | SQL injection | Bound parameters only, inside the `repo` layers; no string-built SQL outside migrations. [Rev-1] The one-off bootstrap also uses chunked bound-parameter statements, never SQL files with literal values | Code review rule + grep check in CI |
| S11 | GitHub Actions abuse (script injection, forks) | Private repo; no `pull_request_target`; PR workflow (`ci.yml`) references **no secrets**; untrusted values are never interpolated into `run:` | Workflow review |
| S12 | Telegram bot token compromised | Rotate with BotFather, update secret, re-run `set-webhook` script; documented in runbook; allowlist limits blast radius to messages sent | Runbook drill once |
| S13 | Repo made public by mistake | Repo private; `claude.md` forbids changing visibility; no source data or secrets in repo regardless | Policy |
| S14 | D1 data loss or corruption | D1 Time Travel point-in-time restore (retention on Free plan to be verified at build); weekly `d1 export` stored as an Actions artifact (30-day retention); everything except predictions can be rebuilt from sources | Restore drill in Essentials 1, Stage 7 |
| S15 | [v3] Hostile or malformed command arguments | Strict grammar (§6.10): token pattern, 64-character cap, control characters removed; dates by pattern plus calendar check; numbers by pattern plus range; a team name is used only as a bound parameter and a comparison string; arguments never echoed or logged | Vitest: injection strings, over-long text, `@bot` suffix, Unicode tricks |
| S16 | [v3] Operational data (run ids, job status, logged predictions) reaches someone else | Commands run only after the same three auth layers; another chat gets no reply (no oracle) and only the counter event; no new route, no new secret | Vitest auth matrix with a command from a stranger |
| S17 | [v3] The command menu tells strangers what the bot does | `setMyCommands` scoped to the allowlisted chat only; the default scope stays empty | Deploy log; manual check from another account (Stage 8) |

**Secrets and tokens inventory** (no value ever in the repo):

| Name | Used by | Stored in | Scope |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Worker (read only by `telegram/` [v2]); fit job (weekly report, alerts); `deploy.yml` (`set-webhook`) | Worker secret; GitHub secret | Bot API |
| `TELEGRAM_WEBHOOK_SECRET` | Worker; `deploy.yml` (`set-webhook`, smoke) [Rev-3] | Worker secret; GitHub secret | Header check |
| `WEBHOOK_PATH_SECRET` | Worker, `set-webhook` script | Worker secret; GitHub secret | Route |
| `ALLOWED_CHAT_ID`, `ALLOWED_USER_ID` | Worker | Worker vars/secrets | Allowlist |
| `TELEGRAM_CHAT_ID` [v2] | fit job (weekly report, alerts), `report` step of `data.yml` only; [v3] the `set-webhook` step of `deploy.yml` (menu scope only) | GitHub secret | The chat the report is sent to (same value as `ALLOWED_CHAT_ID`) |
| `FD_ORG_TOKEN` | fit job, `data.yml` | GitHub secret | football-data.org |
| `WORKER_URL` [Rev-3] | `deploy.yml` (`set-webhook`, smoke) | GitHub secret | Public Worker URL (not a credential) |
| `CF_D1_TOKEN`, `CF_ACCOUNT_ID`, `D1_DATABASE_ID` | fit job (nightly, backtest); local `footy load-csv` runs on Divine's machine (local environment variable, never committed) [Rev-2] | GitHub secrets | **D1 edit only** |
| `CF_DEPLOY_TOKEN` | `deploy.yml` only | GitHub secret (environment secret if available — see §9.7) | Workers deploy + D1 migrations |

### 9.2 Observability

Approach: small, free, and sufficient for one user — structured logs, durable event rows, and push alerts; no external APM.

- **Worker logs:** one JSON line per request (`request_id`, `update_id`, `route`, `outcome`, `duration_ms`, `matches_in/out`, `error_code`). Workers Logs/Observability enabled in `wrangler.toml` (retention on Free to be verified; durable facts go to D1, not logs).
- **Durable events (`events` table):** auth rejections (counter only), unmapped teams, source anomalies, model failures, promotion decisions, CPU-limit hits, send failures. Pruned at 90 days.
- **Job records (`job_runs`):** every CLI step writes start/end/status/rows touched/diagnostics.
- **Alerts (Telegram, deduped per `alert_key` per 24 h):** nightly failure, promotion rejected, model failed, unmapped teams, source anomaly, STALE MODELS, watchdog trigger, CPU-limit exception, unusual auth rejection count.
- **Watchdog (ADR-015):** Worker cron trigger every 6 h reads `active_run.activated_at`; older than 36 h or missing → alert. [Rev-1, ADR-029] It also alerts when any `uploads` row is still `received` after 10 minutes (an upload that was acknowledged but never answered, for example a Worker killed at the CPU limit, which can neither reply nor write an event). This catches the case the nightly workflow's own `if: failure()` alert cannot: the workflow never started (GitHub's documented 60-day inactivity auto-disable applies to **public** repositories and this repo is private [Rev-1]; scheduled runs can still be delayed or dropped).
- **Product metrics:** weekly report (ADR-016) with RPS vs baseline, log loss, calibration bins, per-competition and per-model scores, share of fixtures omitted by reason, and number of scored predictions towards the 300-match target.
- **Health check:** `footy healthcheck` (exit code 0/1) used by the nightly job after publish and by Divine on demand from the Actions tab.
- **[v3] Commands:** the request log line carries `outcome` (`command`, `unknown_command`, `command_usage`, `command_failed`) and the command name when it is a known one, never the arguments; an unexpected failure writes one `command_failed` event (hourly dedupe key). `/status` is the on-demand view of the watchdog and health-check questions; commands are not counted by the nightly health check.

### 9.3 CI/CD

| Workflow | Trigger | Secrets | What it does |
|---|---|---|---|
| `ci.yml` | `pull_request` to `main` | none | Install with lockfiles; lint + typecheck (TS), ruff + mypy (Py); Vitest (Workers pool, local D1); pytest; golden-vector parity test (TS vs Python grids); migration lint (no `DROP`/`RENAME` in the same migration that adds a replacement; migrations apply cleanly to an empty D1 and to the previous schema); gitleaks; "no data files" check (no CSV/JSON dump above size threshold outside `packages/contracts` and `data/`); whole-nightly-job test (ingest, score, fit, publish on synthetic fixtures with a SQLite-backed fake D1 client) [Rev-1] |
| `deploy.yml` | `push` to `main` | `CF_DEPLOY_TOKEN` | Guard: verify head commit belongs to a merged pull request; apply D1 migrations; `wrangler deploy`; run `scripts/set-webhook`; post-deploy smoke (wrong-header request → 401; `/healthz`-equivalent). [v3] `set-webhook` also registers the command menu with `setMyCommands` (scope: the chat in `TELEGRAM_CHAT_ID`, list from `packages/contracts/bot_commands.json`); a failed or skipped menu registration is a logged warning and does not fail the deploy; the webhook registration itself stays fatal |
| `nightly.yml` | `schedule` (`17 1 * * *`, A-3 accepted [Rev-2]) + `workflow_dispatch` | D1 token, Telegram, `FD_ORG_TOKEN` | `ingest → score → fit → publish`, Monday also `report`; step `if: failure()` sends a Telegram alert; `concurrency` group prevents overlapping runs; `timeout-minutes: 45` |
| `data.yml` [Rev-3] | `workflow_dispatch` only, `main` only | `FD_ORG_TOKEN`, D1 token; [v2] `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for `report` only | Manual runs of `footy bootstrap --dry-run`, `footy bootstrap`, `footy ingest`, `python -m footy.repo.d1_probe`, [Rev-4] `footy backtest` (inputs `models`, `test_days`, `half_lives`, `shrinks`), `footy fit` and `footy publish`, and [v2] `footy score` and `footy report --send`; [Rev-4] `FD_ORG_TOKEN` and the legal flag reach only `bootstrap`, `bootstrap-dry-run` and `ingest` (least privilege), [v2] the Telegram variables reach only `report`, and the dry run gets no D1 token; the chosen command reaches the shell only as an environment variable. Scheduled use is `nightly.yml` in Stage 7 |
| `backtest.yml` | monthly schedule + manual | D1 token | [v2] `footy backtest --models dc,pi,bp --fail-on-regression`: walk-forward on stored matches, compared with the baseline and with the previous comparable stored backtest; a regression beyond the tolerance exits 4 (the run shows red, an `alert` event is written; informational, not a deploy block) |
| `backup.yml` [v2, Stage 7] | weekly schedule (Sundays 02:43 UTC) + manual, `main` only | D1 token only | `wrangler d1 export` of the database, a size and content check, kept 30 days as a workflow artifact (private repository); restore drill in `docs/runbook.md` |

Rollback: Worker — redeploy the previous commit (revert PR); model run — repoint `active_run` to a retained `superseded` run (§8.6); schema — forward-only fixes (additive-first rule).

### 9.4 Error handling

- **Principle:** fail closed on auth and validation, fail soft on optional data (shots, one model), never fail silently.
- **Bot:** every error maps to a code from the §6 catalogue and a short human message; unexpected exceptions → `E_INTERNAL` reply (once) and an `events` row; the webhook still returns 200 after a successful acknowledgement so Telegram does not retry.
- **Telegram sends:** on `429` honour `retry_after` (bounded); on other failures retry once; if persisted predictions exist but sending failed, a re-upload of the same file replays from the log.
- **D1:** batched statements are atomic per `batch`; the Worker retries a read once; a failing write after computation → reply `E_INTERNAL` and nothing partial is announced.
- **Fit job:** each CLI step returns exit codes 0/1/2/3/4 (§6.7); a source outage → use stored data, continue, alert (FR-17); a model failure → mark that model `failed`, continue with others (FR-07); all models failed → run `failed`, previous run stays active.
- **Retries/backoff:** D1 REST and source HTTP calls use exponential backoff (max 3 attempts, jitter); no unbounded loops.
- **[Rev-4] Abandoned jobs:** a `job_runs` row still `running` after 60 minutes (the workflow timeout is 45) is closed as `failed` when the next `fit`, `publish` or `backtest` starts, so a killed job leaves no permanent `running` row.

### 9.5 Testing strategy

| Layer | Tooling | Examples |
|---|---|---|
| Unit | Vitest, pytest | markets from grid, Under = 1 − Over, RPS on hand-computed cases, alias normaliser, fixture-key builder |
| Property | fast-check, hypothesis | grid sums to 1, non-negative, monotone overs, 1X2 sums to 1, mirror symmetry |
| Golden vectors | shared JSON in `packages/contracts/golden` | [v2] Regression vectors for the Python grid builders (inputs → grid cells and markets). The TypeScript comparison of version 1 is dropped: there is no TypeScript grid |
| Model correctness | pytest on **synthetic leagues** generated from known parameters | parameter recovery, convergence, walk-forward beats frequency baseline on synthetic truth; optional cross-check against `penaltyblog` as an oracle (dev-only) |
| Repository | Vitest + local D1 (Miniflare/workerd), pytest + SQLite | unique keys, first-row-wins on the fixture key (`ON CONFLICT DO NOTHING`), CHECK failures that raise, atomic pointer, additive migrations |
| Integration / e2e | Vitest with fake Telegram + in-memory file bytes | full upload flow incl. drift, omissions, splitting, replay |
| Contract | JSON-schema fixtures (valid/invalid) | all `E_SCHEMA_*` branches |
| Performance | CPU gate (ADR-013) | 60-match synthetic payload; measured p95 vs 6 ms |
| Security | Vitest | S1–S5 cases |
| Pipeline [Rev-1] | pytest + SQLite fake D1 | whole nightly job (ingest, score, fit, publish) on synthetic data, asserting a promoted run, scored predictions and no unmapped teams |
| Added proof [Rev-1] | Vitest, pytest | two identical uploads at once; IST `+1d` date rollover; `d1_client` retry/backoff and resume; alert dedupe over 24 h; 6.5 s pacing with a fake clock; hand-computed ensemble weights; rounded-probability CHECK property test; text-message usage hint; stuck-upload watchdog; `NO_RESULT` close-out; promotion gate rejects corrupted and jumped runs |
| Commands [v3] | Vitest + local D1, node test, pytest | every command row of §6.10 and every behaviour-matrix row it added; grammar (case, `@bot` suffix, over-long arguments, `/start`); read-only proof (row counts and contents of the logged tables unchanged after every command, invariant 9); a stranger's command ignored; replay of the same `update_id`; failure injection (D1 error, send failure); splitting and the 5-message cap; no argument echoed; `/fixtures` never prints a percentage or a probability; registry equals `bot_commands.json`; alert kind lists equal the Python list and the watchdog's; normaliser vectors equal Python's; `compute_metrics` keeps the `/report` keys; the existing upload tests unchanged and green |

Test data is always synthetic or hand-written; raw third-party data is never committed (ADR-025).

### 9.6 Idempotency

| Operation | Key | Mechanism | Result of repeating it |
|---|---|---|---|
| Webhook update | `update_id` | `processed_updates` PK | 200, no work |
| Prediction creation | `fixture_key` | `UNIQUE` + `ON CONFLICT (fixture_key) DO NOTHING`; first prediction immutable | Same stored numbers returned |
| Upload record | `update_id` | `uploads.update_id` UNIQUE; the file sha256 is stored for audit only [Rev-1] | One row per update; a re-upload is a new update but yields the same predictions |
| Match upsert | (`source`, `source_match_id`) and the reconciliation key | `INSERT … ON CONFLICT DO UPDATE` limited to forward status transitions | Same final state |
| Alias insert | (`source`, `alias_norm`) | `UNIQUE` | No duplicates |
| Model run | `run_id` (ULID/uuid from fit job) | New row each night; promote is a single pointer update | A rerun creates a new run; a repeated promote of the same run is a no-op |
| Forecast row [v2] | (`run_id`, `fixture_key`) | `INSERT OR IGNORE` | A rerun writes only the missing rows; existing rows are untouched |
| Scoring | prediction id | `UPDATE … WHERE status='pending'` | Already scored rows untouched |
| Alerts | `alert_key` + 24 h window | `events` lookup before send | At most one per day per key |
| Migrations | filename order | Wrangler migrations table | Applied once |
| Command [v3] | `update_id` | `processed_updates` PK | 200, no second reply; a new command message reads the current state again (read-only, nothing to repeat) |

### 9.7 Branching discipline (NFR-10, ADR-017)

GitHub Flow: short-lived feature branches (`feat/…`, `fix/…`) → pull request → CI green → merge into `main` → `deploy.yml`. **Claude Code never pushes to `main`**; every change, including docs under `/prd`, `/system_architecture`, `/essentials`, goes on a branch and a PR. Commit messages and PR bodies carry the attribution lines required by the environment.

**Enforcement and a caveat I could not verify:** I believe branch protection rules and environment required-reviewers are not available for *private* repositories on the GitHub Free plan (they need a paid plan). This is stated as a belief, not a verified fact — it is on the build-time verification list (§16). If unavailable, the compensating controls are: (1) `claude.md` rule and a committed `pre-push` hook that rejects pushes to `main`; (2) `deploy.yml` guard step that refuses to deploy a commit that is not the merge of a PR; (3) `CF_DEPLOY_TOKEN` referenced only from `deploy.yml`. Residual risk (a human pushing to `main` from a machine without the hook) is accepted for a single-owner repository and recorded in §15 (R-S3).

### 9.8 Legal and compliance register (gates the build)

Personal, non-commercial, probabilities-only use; no odds, no staking advice, no betting-site integration. Under India's Public Gambling Act framing recorded in PRD_1 §9 this remains personal analytics — *not legal advice*.

| Source / service | How used | Status | Gate |
|---|---|---|---|
| football-data.org (free tier) | Automated nightly API calls, token auth, ≤ 10 req/min | Terms and free-tier history depth **to verify at build**. **[Rev-3] Register signed 2026-10-16 (enable); free plan measured to return 3 seasons (§16)** | `SOURCE_ENABLED_FDORG` default off; set to `1` only by the manual `data` workflow, now that the entry is signed |
| football-data.co.uk | [Rev-2] Files downloaded **by hand** by Divine and loaded locally, for history, shots and Scottish Premiership; no automated fetching | Site wording seen in the design session: intended for private individuals, **not commercial or data-training products using automated bots/scrapers/AI**. Automated fetching is not used. Whether hand downloading for personal use is acceptable is confirmed by the Stage 1 terms check | `SOURCE_ENABLED_FDUK` default off. **A-1 decided [Rev-2, ADR-035].** Path 1 (preferred), if the Stage 1 check confirms hand downloading for personal use is allowed: Divine downloads the files and loads them with `footy load-csv`; `SOURCE_ENABLED_FDUK` stays off permanently and there is no co.uk HTTP client. Path 2 (fallback), if not allowed: football-data.org only, and the Scottish Premiership is dropped from v1 **[Rev-3: path 2 was chosen on 2026-10-16; co.uk is not used]** (SPL matches are then omitted as `INSUFFICIENT_HISTORY`, the screener prompt stops listing SPL, shots stay unused). [Rev-1, ADR-032] The terms check and the football-data.org free-history-depth check are done during Stage 1. If football-data.org history is current-season only, most teams stay under 10 matches (`INSUFFICIENT_HISTORY`) for weeks (warm-up: predictions start as teams reach 10 matches) [Rev-2] |
| soccernews.com and league/UEFA pages | Read by the Claude Project (manual, by Divine) — not by this system | Personal/non-commercial; site is affiliate-linked | Outside system boundary; noted only |
| Telegram Bot API | Messaging | Standard bot use | none |
| Cloudflare, GitHub | Hosting, CI | Free-plan terms | none |

`docs/legal/source_terms_register.md` holds, per source: date checked, URL, quoted clause, decision, who decided. `claude.md` forbids enabling a source flag without a signed entry.

---

## Extensibility & Change-Tolerance
- **Data model:** no destructive change (rename/remove a field or table) lands in the same version as its replacement. The new field/table is added and back-filled first; the old one is only removed in a later version once nothing references it. Every migration is additive-first.
- **API:** existing endpoints never change their accepted input or returned shape in a breaking way. New behavior is added via a new endpoint (e.g. `/v2/...`) or a new optional field — never by mutating an existing contract.
- **Auth:** all authentication/session logic sits behind one internal interface (e.g. `auth.checkSession()`). No other module talks to the auth provider directly. Swapping the provider or scheme only touches this one module.
- **Database:** all persistence access goes through a single data-access/repository layer. No raw queries or ORM calls scattered across business logic. Swapping the database engine or ORM only touches this layer.
- **Feature/Module Removal:** no feature, endpoint, table, or module is deleted outright. It is first marked deprecated in the version that stops actively using it (flagged in the Decision Log, and in code/schema itself — e.g. `@deprecated` annotation, deprecated API response header, or a `deprecated: true` schema comment). It is only physically removed in a later version, once a dependency check across the API layer, repository layer, and frontend consumers confirms nothing still references it. The removal version's changelog must cite which prior version introduced the deprecation flag.

### Conformance mapping for this system (non-normative)

| Rule | How this design satisfies it |
|---|---|
| Data model | `db/migrations/NNNN_*.sql` forward-only, additive-first; migration lint in `ci.yml`; schema-v1 JSON contract versioned by `schema_version`, new versions parsed alongside v1 |
| API | The only public surface is the Telegram webhook plus the file contract. New file schema = `schema_version: 2` handled by a new parser branch; v1 behaviour never changes. Reply wording changes are additive (new lines), never removing fields from a published reply format without deprecation. [v3] Commands are a new, additive surface on the same webhook; the upload contract and its reply are unchanged; the usage hint gains a line; the `/report` read contract (§6.10) changes only by adding keys |
| Auth | `apps/bot/src/auth` (`verifyWebhook`, `checkSession`) is the sole reader of webhook secret and allowlist |
| Database | `apps/bot/src/repo` and `apps/fit/src/footy/repo` are the sole SQL locations; CI grep check for SQL outside those paths |
| Removal | Deprecation flags recorded in ADR log and as `-- DEPRECATED vN` comments / `@deprecated` JSDoc; nothing removed in v1 |

---

## 11. Coding methodology (what Claude Code must follow)

1. **Order of work inside every module:** data model/migration → repository functions → pure domain logic → interface layer → wiring. Pure logic first, I/O last.
2. **Pure core, thin shell.** Grid builders, drift, ensemble weights, scoring, rendering are pure functions with no I/O, so they are unit- and property-testable and portable between languages through golden vectors.
3. **Test-first for numerics:** write the property test and a hand-computed example before the implementation; every model change must keep the synthetic parameter-recovery test green.
4. **Python is the numerical reference, and [v2] the only numerical implementation.** The Worker holds no model arithmetic; it copies stored numbers.
5. **Typed boundaries:** Zod at the Telegram boundary; pydantic or dataclasses with validation at the source boundaries; no `any` / untyped dicts crossing module borders.
6. **No hidden state:** configuration through one `config` module/table (`model_runs.config_json`), thresholds never hard-coded in call sites.
7. **Small PRs:** one essentials build step per PR; each PR updates tests, the relevant doc line, and `/tracker/` entry.
8. **Dependency discipline:** add a runtime dependency only with an ADR line; prefer standard library.
9. **Observability by default:** every new failure path has an error code, a log line and (if user-impacting) an alert.
10. **Never** commit secrets, raw source data, or generated model blobs.

## 12. Fullstack constraints an expert coder must respect

- Cloudflare Workers: no Node filesystem, no long-lived state between requests, CPU ≤ 10 ms, ≤ 50 subrequests, 128 MB memory — use Web APIs only; confirm any npm dependency runs in workerd.
- D1 is SQLite with limits (bound parameters per statement, statements per invocation, row/DB size): batch via `db.batch`, chunk large inserts; test with the local D1 harness.
- D1 REST from Python is slower and rate-limited relative to bindings: bulk upserts in chunks, one transaction-like batch per chunk, resumable steps.
- Time: all stored times are UTC ISO-8601; IST conversion only at render time; fixture date for the key is the **UTC kickoff date**.
- Floating point: grids are Float64 in compute; forecast and `predictions.p_*` columns are stored at full precision; display rounding happens at render; sums are verified before rounding and by CHECK constraints [Rev-1, v2].
- Telegram: text ≤ 4,096 chars, sequential sends, 429 handling, files ≤ 20 MB via `getFile`; `allowed_updates=["message"]`.
- Scheduling: GitHub cron is best-effort and can be delayed or disabled after repository inactivity; the watchdog is the control, not the cron.
- Actions budget: private repo Free plan 2,000 min/month; keep nightly ≲ 15 min.
- Idempotent, resumable batch steps: any CLI step can be re-run safely.

---

## 13. Review, challenge and simplify (design phase 9)

Challenged and **rejected** (kept out of v1 on purpose):

| Idea | Why rejected |
|---|---|
| Cloudflare Queues / Durable Objects | Volume ≈ 50 req/day; `waitUntil` + idempotent log suffices; Free-plan availability unverified; adds moving parts (ADR-023) |
| KV or in-Worker caching layer | D1 reads are tiny; the prediction log is already the cache |
| Staging environment | One user, one Telegram bot; CI + local D1 + smoke test is proportionate; GitHub Flow (ADR-017) |
| Web dashboard | Telegram message + weekly chart covers the success metric; Pages dashboard stays v2 |
| Bot commands (`/status`, `/report`) | Reduces auth/attack surface; weekly push + alerts cover needs; adding later is additive. [v3] Adopted for read-only commands (ADR-049) once the system was live and the push alone proved too little for everyday checks |
| Commands that change state (`/rerun`, `/rollback`, `/publish`, `/void`) [v3] | Need a GitHub or Cloudflare token in the Worker (F3 was rejected for the same reason) and one mistyped message could switch models or damage the calibration record; the Actions tab already does it (ADR-051) |
| Probabilities in `/fixtures` [v3] | Would skip the screener's gates and show numbers that are never logged or scored (ADR-050) |
| Inline keyboards and callback queries [v3] | Need `callback_query` updates and a new webhook registration for little gain over typed commands and the menu |
| Shadow predictions for omitted matches | Complexity and bias risk; omissions are logged with reasons instead (ADR-024) |
| Per-team parameter rows | Would raise D1 reads/writes and complicate atomic promotion; JSON payload per model per run is simpler for 179 current (≈ 240 with history-only) clubs [Rev-1] |
| Machine-learning models (GBM, NN) | Data volume and the "probabilities from goals models" scope; Poisson-family models are the established baseline; revisit only if v1 fails the success metric |
| Running model fits inside the Worker | Impossible within 10 ms CPU (ADR-001) |
| Computing grids in the Worker [v2] | Measured p95 16 ms after the planned trims against a 6 ms target and a 10 ms limit, on a cold isolate nearly every time (ADR-042) |

Simplifications adopted: one grid → all markets; one pointer table for promotion; one `events` table for all observability facts; no cache/queue; no staging.

---

## 14. Decision log (ADR format, cumulative)

Status values: Accepted (locked), Accepted-hypothesis (locked but validated by backtest/measurement later), Open-amendment (needs Divine's confirmation).

| ADR | Decision | Context / why | Alternatives rejected | Consequences |
|---|---|---|---|---|
| 001 | Two runtimes: Python batch on GitHub Actions fits models; TypeScript Worker serves uploads | Workers Free 10 ms CPU cannot fit models; Actions gives numpy/scipy free | Everything in Worker; everything in Python on a server | Duplicate grid maths → golden-vector parity tests |
| 002 | Telegram is the only interface | PRD decision; zero UI cost | Web app | Reply formatting/splitting work |
| 003 | Cloudflare D1 as the single database | Free, SQLite semantics, binding from Worker, REST from Python | Postgres (Supabase) — more setup; KV — no relational queries | D1 limits shape batching (§12) |
| 004 | Immutable model runs + atomic `active_run` pointer | Worker must never see a half-written run; rollback needs retained runs | Overwrite params in place | Retention/pruning job; 30 runs kept |
| 005 | One 13×13 grid per match per model; ensemble = linear pool of grids; all markets derived from it | Consistency across 1X2/O-U; simple math | Separate models per market | Tail beyond 12 goals renormalised |
| 006 | Pi-rating (not Elo) as model 2; mapped to grid via expected goal difference + league total goals | PRD "cross-league pi-rating"; Elo lacks goal margin | Elo | **Accepted-hypothesis:** mapping validated by backtest |
| 007 | Pooled fit across leagues with league offsets and shrinkage; UCL links leagues | Cross-league strength needs a connection | Per-league separate fits | **Accepted-hypothesis:** weak identifiability; per-competition RPS reported |
| 008 | Data sources: football-data.org (fixtures/results/UCL), football-data.co.uk (history, shots, SPL) | Free, cover the 10 competitions | API-Football etc. (paid/limited) | Legal gate §9.8; A-1 decided in Rev-2 (ADR-035) |
| 009 | Rolling 1,095-day training window with exponential time-decay | PRD §5; recency matters | Full history | Half-life tuned in backtest |
| 010 | Results use 90 minutes + stoppage only (`score.regularTime`), else `unverified` | PRD §10; extra time/penalties distort | Full-time incl. ET | Needs source field check at build |
| 011 | Auth = path secret + webhook header + chat/user allowlist behind one `auth` module | Single user; layered cheap controls | Telegram login widget; passwords | Locked extensibility rule satisfied |
| 012 | Idempotency: `update_id` dedupe; first prediction per `fixture_key` immutable; key = `date|comp|home_id|away_id` | Retries and re-uploads must not change history | Using the screener `match_id` (opaque, unstable format) | Same numbers on re-upload |
| 013 | CPU risk handled by a measured gate (p95 ≤ 6 ms) and F1→F3 fallback ladder; acknowledge fast, compute via `waitUntil` only to avoid Telegram retries | `waitUntil` does not lift the CPU limit — PRD rationale corrected | Assume it fits | **Accepted-hypothesis:** spike in Essentials 1 Stage 1. **[Rev-3] Gate failed after F1 (p95 16 ms). [v2] Resolved by ADR-042 (nothing to compute in the Worker); re-measured on the lighter workload in Essentials 2 Stages 5b and 7** |
| 014 | Repository layers (TS, Python) own all SQL; forward-only additive migrations | Locked extensibility rules | ORM everywhere | CI grep check |
| 015 | Watchdog cron in the Worker + STALE MODELS banner (> 36 h) | Scheduled workflows can silently not run | Rely on Actions failure alert | Worker has a scheduled handler |
| 016 | Weekly calibration report pushed by the fit job as message + chart; no bot commands in v1 | Smaller attack surface | `/report` command | Additive later. [v3] Superseded in part by ADR-049: a read-only `/report` text command exists; the weekly push and its chart stay |
| 017 | GitHub Flow, no staging; PR required; Claude Code never pushes to `main` | Project rule; single owner | Gitflow, staging | Free-plan enforcement caveat (§9.7) |
| 018 | Two Cloudflare tokens: nightly = D1 only; deploy token separate | Least privilege | One token | A-2 accepted [Rev-2]; PRD wording updated |
| 019 | Models implemented in-house (numpy/scipy); `penaltyblog` only as optional test oracle; a model failing sanity checks is stored `failed`, not silently replaced | Control, minimal deps; failure must be visible | Depend on penaltyblog at runtime; reuse yesterday's params | Own correctness tests needed |
| 020 | Ensemble weights = softmax of negative rolling RPS, shrunk to equal weights while few matches are scored | Avoid noisy weights early | Fixed weights; best-model-only | κ, N, shrinkage constants are starting values (**hypothesis**) |
| 021 | Drift: goals ±0.6 per match, shots ±25% relative (≥ 8 of last 10 with shots); all thresholds "unvalidated" and stored per run | PRD requires a drift filter but gives no numbers | Statistical test per team | Thresholds tuned via backtest |
| 022 | Promotion gate with sanity checks before switching `active_run` | Registry/promote pattern (RESOURCE 3) | Auto-activate | Rejected runs alert |
| 023 | No cache layer and no queue in v1 | Volume and complexity | KV, Queues | Revisit if CPU gate forces F2 |
| 024 | Omissions are logged with reason codes; no shadow predictions | Scope | Predict everything silently | Coverage statistics only |
| 025 | Raw source data never committed; tests use synthetic data | Licensing and repo hygiene | Fixture dumps | Synthetic generators are test code |
| 026 | [Rev-1] v1 drift is goals-only; the shots check and shots columns are deferred until A-1 is decided | Shots come only from legal-gated co.uk and are optional in the PRD ("where available") | Build shots now | Additive later (nullable columns exist); refines ADR-021 |
| 027 | [Rev-1] History-only clubs live in `data/historical_teams.json`, seeded as `active=0` with per-source aliases | The 3-year window contains clubs outside the 2026-27 list; dropping their matches loses data and league links | Drop those matches | One more data file; Stage 2 counts = 179 active + listed |
| 028 | [Rev-1] A pending prediction with no matching finished match 3 days after kickoff becomes void `NO_RESULT` | A rescheduled match changes the key date | Leave pending forever | New void reason; one deduped alert |
| 029 | [Rev-1] `uploads` row is written as `received` first; the watchdog alerts on uploads stuck over 10 minutes | A Worker killed at the CPU limit can neither reply nor log | Rely on exceptions | Small watchdog extension |
| 030 | [Rev-1] Promotion gate = structural checks + stability guard; no performance comparison in v1 | The 14-day comparison is in-sample for the new run | 14-day walk-forward score, or 14 extra fits per night | Supersedes the gate wording of ADR-022; out-of-sample evidence comes from scored predictions |
| 031 | [Rev-1] Bootstrap uses chunked bound-parameter statements via `d1_client.py`; no SQL files with literal values | Locked rule: bound parameters only (S10) | SQL files | Slower once (minutes), resumable |
| 032 | [Rev-1] Source-terms and free-history-depth checks are done as notes during Stage 1 | A negative answer should arrive before ingestion is built | Check at the start of Stage 2 | No code; A-1 stays Divine's |
| 033 | [Rev-1] Each stage creates the tables it first needs | Merged migrations are never edited; early guesses would force patch migrations | All 16 tables in Stage 1 | More, smaller migration files |
| 034 | [Rev-1] The UCL final is treated like any match; the UCL note says it may be neutral; no `NEUTRAL_VENUE` code | The bot cannot detect it (no venue field); one match a year | Omit via a date list | Resolves the GR-22 vs R-M6 conflict |
| 035 | [Rev-2] A-1 decided: football-data.co.uk is never fetched automatically; its CSV files are hand-downloaded and loaded locally with `footy load-csv` if the Stage 1 terms check allows it; otherwise football-data.org only and the Scottish Premiership is dropped | Site terms bar automated bots and AI data-training use; the decision rule was set by Divine | Automated co.uk fetching; football-data.org only from the start | Weekly manual file load for SPL freshness; no co.uk HTTP client in the nightly job |
| 036 | [Rev-2] A-3 and A-4 accepted: nightly cron `17 1 * * *` (01:17 UTC, 06:47 IST); reply p95 ≤ 30 s from upload to first message | GitHub delays top-of-hour schedules; a testable latency target | `0 1 * * *`; no target; 15 s target | NFR-11 |
| 037 | [Rev-3] Direction chosen by Divine on 2026-10-16 after the failed CPU gate: the nightly job pre-computes and stores each upcoming match's numbers and the Worker looks them up. **[v2] Designed in ADR-042 and §8.11** | Production p95 16 ms after F1 against a 6 ms target; uploads are about daily so requests are cold | F2 split, F3 offload to Actions, Workers Paid plan, accept the risk | Implemented by version 2 |
| 038 | [Rev-3] Stage 2 data commands run as a manual `data` workflow (`workflow_dispatch`, main only) with `SOURCE_ENABLED_FDORG` set in that workflow, until `nightly.yml` exists in Stage 7 | Lets bootstrap, dry-run, ingest and the D1 probe run with stored secrets and no pasting | Run locally with pasted tokens | One more workflow to maintain; the flag is set only after the register entry is signed |
| 039 | [Rev-4] Extreme-fixture guard: goal rates clipped to 0.01..6 and the Dixon-Coles rho clamped to its feasible interval when a grid is built; the bivariate Poisson covariance is floored at 1e-4, below its fit bound | A fitted rho with a rate near 5 made a correction factor negative and crashed a test backtest | Reject the fixture; clamp rho inside the fit only | Part of the Python reference and the golden vectors; any other implementation must match |
| 040 | [Rev-4] The ensemble shrinks toward the backtest-derived weights when available (equal weights otherwise); kappa = 100 | Section 8.3 says the initial weights come from the backtest but shrinks toward 1/M; kappa has to suit RPS differences of about 0.003 | Shrink to 1/M only; kappa = 1 | Starting values, unvalidated |
| 041 | [Rev-4] `team_form` has a row for every active team; the promotion gate numbers are fixed (coverage 95%, payload coverage 95%, stability bound 0.5) | Teams without matches must be omitted as INSUFFICIENT_HISTORY, and the coverage check must be satisfiable | Rows only for teams with matches | Thresholds stored in `config_json`, unvalidated |
| 042 | [v2] The nightly job stores one forecast row per scheduled fixture in the next 5 days (ensemble and per-model 1X2 and total-goals pmf, history/drift verdict, baseline) in `fixture_forecasts`; the Worker looks the row up and copies it into `predictions`; a missing row is `NO_FORECAST`, never computed in the Worker | The CPU gate failed (ADR-013, ADR-037); the Worker needs only markets; promotion and rollback should move parameters and forecasts together | Store full 13×13 grids (3× the size, no extra use); F2 split invocations; F3 offload to Actions (20–60 s latency, GitHub token in the Worker); Workers Paid plan (cost) | New table and migration `0004`; TypeScript grid port and its golden-vector parity are dropped; gate checks forecast rows; forecasts kept for the newest 5 runs; `NO_FORECAST` for fixtures outside the window |
| 043 | [v2] The Worker calls the Telegram Bot API with plain `fetch` and has no grammY | Trim step F1 allows dropping grammY features; the calls needed are four (`getFile`, file download, `sendMessage`, nothing else); fewer bytes and CPU, no dependency, easy to fake in tests | grammY `api` wrapper | `telegram/client.ts` owns 429 handling and token redaction; PRD_2 stack row updated |
| 044 | [v2] History and drift verdicts are computed once, in Python, at forecast time and stored | A TypeScript copy would need its own parity tests and CPU | A TypeScript `drift` module | Thresholds stay in `config_json`; verdict and statistics are visible in the reply |
| 045 | [v2] `predictions` are self-contained; `predictions.run_id` has no foreign key | Pruning runs older than 30 (ADR-004) would otherwise fail on predictions that reference them, and predictions must outlive their run | Keep every run; cascade-delete predictions | Baseline and forecast values are copied into each prediction; `run_id` is for display and audit |
| 046 | [v2] Rolling per-model RPS from logged predictions feeds the next fit's ensemble weights; weekly report with paired bootstrap interval; `calibration_snapshots`; backtest regression check against the previous comparable stored backtest (tolerance 0.003 RPS) | Stage 6 of the build plan; ADR-020 asks for rolling weights | Compare with a committed metrics file (needs a commit to update) | Alignment rule: a prediction enters a model's history only if every fitted model forecast it; tolerance is a starting value, unvalidated |
| 047 | [v2] The Worker validates the screener file with a hand-written validator (`intake/validate.ts`) instead of running Zod at request time; `intake/schema.ts` (Zod) remains the contract and generates the JSON Schema | Stage 5b CPU gate missed on the first production run (7 to 9 ms warmed, 11 to 25 ms cold, target 6); F1 trim of the validation work is the next step of the ladder (§8.10) and the cost is fixed per request | Workers Paid plan; F2/F3 (not adopted); accept the miss | Differential test (thousands of mutated files: same verdict, issue paths and codes, parsed data); Zod is no longer in the Worker bundle |
| 048 | [v2] Divine accepted the missed CPU target on 2026-10-18 and chose to proceed to Stage 7 | After the F1 trim: warmed 5 to 8 ms (target 6), first request 14 to 17 ms (Free-plan limit 10); no request failed in 26 production requests; the remaining cost is fixed (Telegram, D1, hash, start-up) | Workers Paid plan (new architecture version); more trims (about 1 ms, uncertain) | Silent upload at worst, resent by Divine; nothing lost or wrong; watchdog alert for an upload stuck in `received` (Stage 7). Revisit with the paid plan if it ever happens |
| 049 | [v3] Read-only bot commands: `/help` (`/start`), `/status`, `/fixtures`, `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team`, `/alerts`, in a `commands/` module over a read-only `QueryRepository`; `/status` reuses the watchdog's `collectFindings` | Once live, checking the system meant opening GitHub or waiting for an alert or the Monday report; every answer is already stored | No commands (ADR-016 as it was); a web dashboard (a second surface and cost); a separate admin bot (a second token and allowlist) | One new module and repository interface; no migration; the alert predicate and the name normaliser are pinned across languages by checks |
| 050 | [v3] `/fixtures` shows verdicts only, never probabilities (Divine, 2026-11-21) | Probabilities without the screener skip gates G1 to G6 and are never logged or scored | Show the stored probabilities as a preview | The upload stays the only way to see and log a fixture's numbers |
| 051 | [v3] No state-changing commands; no GitHub or Cloudflare token in the Worker | A token in the Worker widens the blast radius of a compromise (F3 was rejected for it); a typed command could switch runs or void predictions by mistake | `/rerun` with a fine-grained `actions:write` token; `/rollback` and `/void` from chat | Re-runs, rollbacks and publishes stay in the Actions tab; revisit only as a new version |
| 052 | [v3] One command list in `packages/contracts/bot_commands.json`, used by the registry and by `setMyCommands` at deploy, scoped to the allowlisted chat; a menu failure does not fail the deploy | The menu and the registry must not drift; strangers should not see the menu; a cosmetic failure should not block a fix from shipping | Hard-code the list twice; default menu scope | `deploy.yml` passes `TELEGRAM_CHAT_ID` to `set-webhook`; registry test |

**Amendments decided by Divine on 2026-10-16 [Rev-2]:** A-1 decided (ADR-035: hand-downloaded co.uk files if the Stage 1 check allows it, otherwise football-data.org only and the Scottish Premiership dropped); A-2 accepted (two Cloudflare tokens, ADR-018); A-3 accepted (cron `17 1 * * *`, ADR-036); A-4 accepted (reply p95 ≤ 30 s, NFR-11, ADR-036). **[Rev-3] A-1 resolved on 2026-10-16/17: path 2 (football-data.org only, Scottish Premiership dropped).** Only open item: whether the Stage 1 terms check allows hand downloading, which selects path 1 or path 2 of A-1.

---

## 15. Risks and mitigations (design phase 8/9)

### 15.1 Security (see §9.1 for controls)

S1–S14 as in the threat table. Additional residual risk: **R-S3** — branch protection may be unavailable on a private Free repo (§9.7); mitigated by hook, deploy guard and policy.

### 15.2 Performance and capacity

| ID | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R-P1 | Worker exceeds 10 ms CPU on a large upload | Medium / Low (a silent upload, resent; nothing lost or wrong) [v2: no model arithmetic in the Worker; measured 2026-10-18: warmed 5 to 8 ms, first request 14 to 17 ms, no failure] | Accepted (ADR-048); cost does not grow with the file; hard cap 100 matches; Stage 7 watchdog alerts on an upload stuck in `received`; paid plan as fallback |
| R-P2 | Subrequest limit (50) exceeded by many reply messages | Low / Medium | Chunking at block boundaries; worst case 29 (§3.4); count in tests |
| R-P3 | D1 statements per invocation (50) exceeded | Low / Medium | Batched repo calls; test counting statements |
| R-P4 | D1 REST latency or rate limits slow the nightly job | Medium / Low | Chunked upserts, resumable steps, timeout 45 min |
| R-P5 | Dixon-Coles fit fails to converge | Medium / Medium | Warm start from previous run, bounds, regularisation; model marked `failed` visibly |
| R-P6 | Actions minutes exhausted | Low / Medium | ≈ 30% of budget used (§3.5); backtest monthly only |
| R-P7 | football-data.org 10 req/min limit breached | Low / Low | Pacing ≥ 6.5 s; one request per competition |
| R-P8 | Telegram 429 on bursts | Low / Low | Sequential sends, `retry_after` |
| R-P9 | D1 size growth | Low / Low | < 40 MB year 1; pruning of runs and events |
| R-P10 | Cold start latency | Low / Low | Workers cold starts are small; measured in smoke |
| R-P11 | Large payload parse cost | Low / Low [v2: the Worker no longer reads model payloads] | Forecast rows only |
| R-P12 | Floating-point drift between TS and Python | Not applicable in v2 (one implementation) | Python tests and database CHECK constraints on the stored numbers |
| R-P13 | [v3] A command exceeds the 10 ms CPU limit (for example `/team` on a cold isolate) | Low / Low (a silent reply, sent again; nothing written) | Measured in Stage 8; F1 trims (fewer rows, simpler rendering); at most 2 D1 batches |

### 15.3 Reliability and operations

| ID | Risk | Mitigation |
|---|---|---|
| R-O1 | Nightly workflow never runs (GitHub delay or skip; the 60-day inactivity auto-disable is documented for public repos only [Rev-1]) | Watchdog + STALE MODELS banner (ADR-015) |
| R-O2 | Source format change breaks parsing | Parser contract tests, anomaly rule fails the run, previous run stays active |
| R-O3 | Team renames / promotions / season rollover leave unmapped teams | Alias table + deduped alert + canonical list update procedure each summer |
| R-O4 | Divine forgets to upload / Claude Project output drifts from schema | Schema-v1 validation with clear errors; PRD §10 handling; `excluded[]` has no `match_id` observation recorded in §4.2 for the screener prompt |
| R-O5 | Replies sent without log row | Persist-then-reply ordering (§7.10) |
| R-O6 | [Rev-1] Upload acknowledged but never answered (Worker killed at the CPU limit) | `received` row plus watchdog alert (ADR-029) |
| R-O7 | [v2] Fixtures reach the screener's list that the nightly job did not forecast (late additions, a missed or failed nightly run) | `NO_FORECAST` is shown with its count in the footer; 5-day window; STALE MODELS banner; Stage 7 watchdog alerts when the active run has no forecasts for today |
| R-O8 | [v3] A command's view and the watchdog or report disagree | `/status` calls the watchdog's `collectFindings`; `/report` shows the stored snapshot; the alert predicate and the normaliser are pinned by checks (§8.12) |

### 15.4 Model and product

| ID | Risk | Mitigation |
|---|---|---|
| R-M1 | Models do not beat the frequency baseline | That outcome is a valid result of the success metric; 300-match gate; fall back to reporting baseline-calibrated probabilities |
| R-M2 | Overfitting of ensemble weights to few matches | Shrinkage toward equal weights (ADR-020) |
| R-M3 | Drift thresholds arbitrary | Marked unvalidated in every reply until backtested (ADR-021) |
| R-M4 | Cross-league pooling mis-scales UCL matches | Per-competition RPS; UCL note in replies (ADR-007) |
| R-M5 | **SPL data staleness** (co.uk files are hand-loaded, so SPL data is as fresh as Divine's last load; fd.org free tier does not cover SPL) [Rev-2] | `team_form.latest_match_date` note in replies; INSUFFICIENT_HISTORY rule; dropped under path 2 of A-1 (ADR-035) |
| R-M6 | **Neutral-venue UCL final** is modelled with home advantage | [Rev-1, ADR-034] The bot cannot detect it (the file has no venue or stage field), so it is treated like any match and the UCL reply note says the final may be at a neutral ground. No `NEUTRAL_VENUE` omission |
| R-M7 | Reliability gates (screener) selection bias distorts baseline | Baseline computed over the same published set; omissions logged |
| R-M8 | Probabilities misread as betting advice | Footer disclaimer: probabilities, not advice; no odds, no stake language |
| R-M9 | [v3] A `/fixtures` verdict `ok` is read as "the match will be predicted" or as a tip | The footer says verdicts only and that the screener's gates still decide; no probability is shown (ADR-050) |

### 15.5 Legal

R-L1 co.uk terms for hand downloading (§9.8, checked in Stage 1; no automated use) [Rev-2]; R-L2 football-data.org terms/redistribution (personal use, nothing republished); R-L3 gambling-law framing (personal analytics only; not legal advice).

---

## 16. Verification ledger

**Verified during the design session (re-verify at build — limits change):**
- Workers Free: 10 ms CPU per invocation, 50 subrequests, 100,000 requests/day; `waitUntil` does not lift the CPU limit.
- D1 Free: 5M rows read/day, 100k rows written/day, 500 MB per database, 5 GB per account, 50 queries per invocation.
- Telegram `getFile` downloads up to 20 MB; text messages ≤ 4,096 characters.
- GitHub Free private repositories: 2,000 Actions minutes/month.
- football-data.org free tier: 12 competitions, 10 requests/minute, delayed scores.
- football-data.co.uk: all nine domestic leagues, shots from 2017/18, updated about twice weekly, no UCL.
- grammY supports Cloudflare Workers via `webhookCallback(bot, "cloudflare-mod", { secretToken })`. [v2] Not used (ADR-043).
- `penaltyblog` implements Dixon-Coles, bivariate Poisson, RPS and time-decay weights (used only as optional test oracle).
- [Rev-1, checked during the engineering review] GitHub docs state the 60-day scheduled-workflow auto-disable for **public** repositories; environments and environment secrets for private repositories need a paid plan (not available on Free); CPU time and wall time appear in the Workers Logs invocation log.

**Verify at build (cannot be assumed):**
1. football-data.org free-tier history depth, field availability (`score.regularTime`, `duration`) and written terms.
2. football-data.co.uk terms for hand downloading for personal use (no automated fetch is planned, Rev-2); CSV column headers per division; availability of earlier UCL seasons from any free source.
3. D1 REST API batch support and the 100-bound-parameter limit per statement.
4. Workers Logs retention on the Free plan; D1 Time Travel retention on Free.
5. GitHub: branch protection availability on private Free repos (§9.7). [Rev-1] Environments and environment secrets are documented as unavailable on Free private repos, and the inactivity auto-disable is documented for public repos only; confirm both once.
6. soccernews.com terms for Divine's manual use.
7. Worker CPU time of the real engine (ADR-013 spike).
8. Pi-rating constants from Constantinou & Fenton (2013) — transcribe from the paper, test against hand examples.

[Rev-1, ADR-032] Items 1, 2 and 6 are checked during Stage 1, not at the start of Stage 2.

**[Rev-3] Outcomes recorded 2026-10-17 (details in `docs/verification.md`):**
- Item 1: football-data.org free plan returned all three seasons requested (2024-25, 2025-26, 2026-27) for all nine competitions it covers (9,280 matches); `score.regularTime` and `score.duration` exist; `fullTime` includes extra time and the shootout; written terms were not found and the entry was signed on the stated free-plan use.
- Item 2: resolved by decision, not by a permission: A-1 path 2, co.uk not used. CSV headers were therefore never needed.
- Item 3: the D1 REST API accepted batches of 10 statements and statements of up to 100 bound parameters in the production bootstrap. Batch atomicity is still not confirmed against the live service.
- Item 7: Worker CPU gate failed (p95 22 ms, then 16 ms after F1); see §8.10 and ADR-037.

**[Rev-4] Outcomes recorded 2026-10-17 (details in `docs/verification.md` sections 5 and 6):**
- Item 8: pi-rating constants verified (lambda 0.035, gamma 0.7, b 10, c 3, psi = 3 log10(1+e)). The exact formula rests on the paper's prose, the author's 2022 restatement and the CRAN implementation, because the PDF's equations did not extract as text.
- Stage 3 backtest (production, 2,533 matches): Dixon-Coles RPS 0.2044 against the baseline's 0.2309, ahead in all nine competitions.
- Stage 4 comparison (2,861 matches): baseline 0.2304, pi 0.2076, dc 0.2042, bp 0.2042, ensemble 0.2040; all beat the baseline in every competition; dc, bp and the ensemble are statistically tied. Not a validation.
- Item 3: batch atomicity is still not tested against the live service.

**[v2] Verify at build for Essentials 2:** (a) D1 accepts `INSERT ... SELECT ... FROM json_each(?1)` with one JSON bound parameter of up to about 200 KB (the Worker uses it to insert up to 100 predictions in one statement); verified by the Vitest run on local D1 and to be confirmed on the live service in the Stage 5b real upload. (b) Worker CPU p95 for 15, 60 and 100 matches with no model arithmetic (Stage 5b gate). (c) `sendPhoto` multipart upload from `requests` works for the weekly chart (Stage 6 live report). (d) `TELEGRAM_BOT_TOKEN` is set as a Worker secret (manual step in `docs/setup.md`).

**[v3] Verify at build for Essentials 3:** (a) `setMyCommands` with `scope: {type: "chat", chat_id}` shows the menu in the private chat and not to another account; (b) Telegram sends `/start` and menu taps as plain `message.text` (with an optional `@bot` suffix) under `allowed_updates=["message"]`; (c) the CPU of `/status`, `/fixtures` and `/team` on production (Workers Logs `cpuTime`).

**Source-file finding:** `SYETEM DESIGN RULES.html` in the project contains only a saved, empty claude.ai chat shell — no rules. Operative rules therefore come from the project instructions, `system_architecture.md.md` (house format), the C4 resource, and the other resources. Divine should re-upload the intended rules file if it exists.

---

## 17. Sources

**Project resources (single source of truth):** project instructions; `system_architecture.md.md`; C4 models and diagrams resource; AI-systems design resource (RESOURCE 3: batch-train/online-serve split, model registry and promotion, monitoring loop); ByteByteGo system design archive and the system-design blueprint PDF (scale estimation, caching/queue trade-offs).

**External references consulted in the design session (re-check at build):**
- Cloudflare Workers limits — developers.cloudflare.com/workers/platform/limits
- Cloudflare D1 limits and REST API — developers.cloudflare.com/d1
- grammY hosting on Cloudflare Workers — grammy.dev/hosting/cloudflare-workers
- Telegram Bot API — core.telegram.org/bots/api
- football-data.org v4 documentation — docs.football-data.org
- football-data.co.uk data and notes — football-data.co.uk
- GitHub Actions billing and limits — docs.github.com
- penaltyblog — github.com/martineastwood/penaltyblog
- Dixon, M. J. & Coles, S. G. (1997), *Modelling Association Football Scores and Inefficiencies in the Football Betting Market*, JRSS C.
- Karlis, D. & Ntzoufras, I. (2003), *Analysis of sports data by using bivariate Poisson models*, JRSS D.
- Constantinou, A. C. & Fenton, N. E. (2013), *Determining the level of ability of football teams by dynamic ratings based on the relative discrepancies in scores between adversaries*, JQAS; and (2012) *Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models*, JQAS (RPS).

---

## 18. Review amendments (Rev-1, 2026-10-16)

Applied in place after `/plan-eng-review`, at Divine's explicit instruction. The ten answered review decisions and eight corrections are folded into the sections above and tagged `[Rev-1]`. The version number stays 1. **Rev-2 (same day)** records Divine's decisions on A-1 to A-4, tagged `[Rev-2]`.

| Ref | Change | Where |
|---|---|---|
| D3 / ADR-026 | Drift is goals-only in v1; shots check, coverage rule and shots columns deferred until A-1 | §5.3, §5.4, §8.4, §8.8, GR-14, GR-18 |
| D4 / ADR-033 | Each stage creates its own tables; Stage 1 `0001` has only `processed_updates`, `uploads`, `events`, `job_runs` | §5 intro |
| D5 / ADR-027 | History-only clubs in `data/historical_teams.json`, `active=0` | §5.2, §7.6, §8.5, GR-23 |
| D6 / ADR-032 | Source-terms and free-history-depth checks as notes during Stage 1 | §8.5, §9.8, §16 |
| D7 / ADR-029 | `uploads` row written as `received` first; watchdog alerts if stuck over 10 minutes | §5.5, §6.2, §6.3, §7.10, §9.2, GR-25 |
| D8 / ADR-028 | Pending predictions with no result 3 days after kickoff become void `NO_RESULT` | §5.5, §7.11, §8.7, GR-24 |
| D9 / ADR-030 | Promotion gate = structural checks + stability guard; no performance comparison in v1 | §8.6, GR-26 |
| D10 / ADR-031 | Bootstrap via chunked bound-parameter statements; no SQL files | §6.7, §6.8, §9.1 S10, GR-27 |
| D11 / ADR-034 | UCL final treated like any match; no `NEUTRAL_VENUE` | §8.8, §15 R-M6, GR-22 |
| D12 | Whole-nightly-job test on fake data in `ci.yml` | §9.3, §9.5 |
| D13 | Parked idea: pre-computed grids as a CPU fallback (tracker note, not a decision) | §8.10 |
| C1 | Zod strips unknown keys (not `.strict()`) | §9.1 S4 |
| C2 | `predictions.p_*` stored at full precision; only `grid_json` rounded | §5.5, §12 |
| C3 | CPU measured from Workers Logs `cpuTime` | §8.10 |
| C4 | 60-day auto-disable is documented for public repos only | §9.2, §15 R-O1, §16 |
| C5 | Team count is 179 (168 domestic + 11 UCL-only), not about 130 | §3.3, §3.6, §5.2, §13 |
| C6 | "Phase" wording in the essentials corrected to "Stage" | essentials |
| C7 | `uploads` unique key is `update_id` only | §9.6 |
| C8 | Golden vectors compare cells within 1e-9; no cross-language hash | §8.1, §9.5 |
| Tests | Added proof for approved behavior (concurrency, IST rollover, `d1_client` retry/resume, alert dedupe, pacing, ensemble weights, rounding CHECK, usage hint) | §9.5 |
| A-1 / ADR-035 (Rev-2) | co.uk never fetched automatically; hand-downloaded files loaded with `footy load-csv`; fallback football-data.org only with SPL dropped | §4.3, §6.7, §6.8, §7.2, §7.4, §8.5, §9.1, §9.8, ADR-035 |
| A-2 (Rev-2) | Two Cloudflare tokens accepted | §4.3, ADR-018 |
| A-3 (Rev-2) | Nightly cron `17 1 * * *` (01:17 UTC, 06:47 IST) accepted | §4.3, §7.5, §7.9, §9.3, ADR-036 |
| A-4 (Rev-2) | Reply p95 ≤ 30 s accepted as NFR-11 | §2.2, §4.3, ADR-036 |

A-1 to A-4 are decided (Rev-2). [Rev-3] A-1 resolved to path 2.

### Rev-3 (2026-10-17): outcomes of the Stage 1 and Stage 2 builds

Recorded at Divine's explicit instruction after a code review of Stages 1 and 2. No requirement changed in this version; direction changes are logged as decisions and handed to design chat.

| Ref | Change | Where |
|---|---|---|
| ADR-037 | CPU gate failed after F1; Divine chose pre-computed grids; redesign pending in PRD_2 / architecture_2 | §8.10, §14 |
| A-1 outcome | Path 2: football-data.org only, co.uk unused, Scottish Premiership dropped; free plan returns 3 seasons | §4.3, §9.8, §16 |
| §8.5 | One-source disagreement rule, forward-only status protection, `fullTime` caveat | §8.5 |
| ADR-038 | Manual `data` workflow for Stage 2 commands | §7.6, §9.3, §14 |
| Inventory | `TELEGRAM_WEBHOOK_SECRET` and `WORKER_URL` are also GitHub secrets | §9.1 |
| Ledger | Verify-at-build items 1, 2, 3 and 7 resolved or answered | §16 |

### Rev-4 (2026-10-17): outcomes of the Stage 3 and Stage 4 builds

Recorded at Divine's explicit instruction after the live runs and a code review of Stages 3 and 4. No requirement changed in this version. Review findings that are open are tracked in `/tracker/`, not here.

| Ref | Change | Where |
|---|---|---|
| ADR-039 | Extreme-fixture guard (rate clip, rho clamp); the 1e-6 tail claim measured to hold up to about 2.3 goals per side | section 8.1, section 14 |
| As built | Shared pooled parameterisation, no warm start, optimiser cap 3000 and tolerance 1e-10, pi-rating constants and fitted scale, window ends at the data cut-off | section 8.2 |
| ADR-040 | Ensemble prior from the backtest, kappa 100 | section 8.3, section 14 |
| ADR-041 | `team_form` for every active team; as-built gate, promotion batch, pruning and rollback | sections 5.4 and 8.6, section 14 |
| CLI | `backtest`, `fit`, `publish` options; exit code 4 cases; legal gate only for data commands; `data.yml` commands | sections 6.7 and 9.3 |
| Structure | `backtest/`, `fitting.py`, `models/*`, `repo/{training,models}.py`, Worker `runs.readActive` | section 7.6 |
| Ledger | Item 8 verified; Stage 3 and 4 backtest results | section 16 |
| Review fixes | Covariance floor; prior only from a matching backtest; gate cannot be skipped by omission and ignores a corrupt active run; `--accept-drift`; abandoned-job sweep; least-privilege `data.yml`; cached active-run read in the Worker; shared model, job and payload code | sections 7.6, 8.1, 8.3, 8.6, 9.3, 9.4, 14 |

## 19. Version 2 (2026-10-17): nightly pre-computed forecasts

The version-2 design is the changelog at the top, §5.4 (`fixture_forecasts`), §5.5 (predictions without a grid, `NO_FORECAST`), §6.5 and §6.7 (modules and commands), §7 (diagrams and structure), §8.4 (drift in Python), §8.6 (gate), §8.7 (copy-on-insert, scoring, report), §8.10 and §8.11 (CPU and the forecast step), §9 (secrets, workflows, tests), §14 (ADR-042 to ADR-046) and §15 (R-P1, R-O7). Items still to be decided by Divine are the same open items as before (the `claude.md` in-place-edit wording, the missing rules file, git identity); nothing in version 2 needs a new decision from Divine.

### 19.1 As built (2026-10-17, Stages 5a, 5b and 6)

Differences between the text above and the code, found while building. None changes a requirement.

| Where | As built |
|---|---|
| §6.1 business checks, order | A fixture that is **already in the log** is shown from the log before the time checks, so a re-upload after kickoff still returns the stored numbers marked "already logged"; a new fixture then goes `DATE_MISMATCH`, `STARTED`, `TOO_FAR`, `UNMAPPED_TEAM`, `DUPLICATE_PAIR`, forecast lookup. `home` equal to `away` is rejected by the schema (fatal), not omitted |
| §5.5 `omissions` | The unique key is (`upload_id`, `label`); a repeated `match_id` is stored under the next free numbered label (`<match_id>#2`, `#3`, skipping any id that really occurs in the file), so every omission keeps a row. `DUPLICATE_PAIR` covers a repeated label and the same fixture listed twice, also when that fixture is already in the log |
| §5.5 insert | The prediction insert is `INSERT ... ON CONFLICT (fixture_key) DO NOTHING`, not `INSERT OR IGNORE` (which also skips rows that break a CHECK). A bad row raises, the batch (predictions, omissions, upload close) rolls back and the pipeline answers `E_INTERNAL` with an id. The fit side still uses `INSERT OR IGNORE` for forecast rows, where a skipped row makes the stored count fall short and the gate rejects the run |
| §6.5 Worker | `handleFetch(request, env, ctx, services)`; `Services` carries `fetch`, `now`, `newErrorId` and `sleep` so tests inject a fake Telegram. Team names are resolved by **exact canonical name** (the contract says canonical); an alias fallback is not built |
| §6.5 `intake` | `scripts/gen-screener-schema.mjs` writes `packages/contracts/screener_v1.schema.json` from the Zod schema; `scripts/contracts.test.mjs` fails if the two differ. `MAX_MATCHES` lives in `intake/schema.ts` so the generator loads it under plain Node |
| §8.7 reply | Team names in a published block come from the file only after they resolved to the canonical table; omitted lines show sanitised file text (control and direction characters removed, length capped) |
| §8.11 | `footy fit` builds forecasts after `team_form` and records `n_forecast_fixtures`; there is no separate `footy forecast` command (a rerun of `fit` and `publish` is the way to refresh them) |
| §9.1, §9.3 | New GitHub secret `TELEGRAM_CHAT_ID`; `matplotlib 3.11.2` joins the pinned Python dependencies; `data.yml` gained `score` and `report`; `backtest.yml` is monthly with `--fail-on-regression` |
| §8.3, ADR-046 | `fit` reads the newest `3 x 200` scored predictions and keeps those every fitted model forecast; the weights use the last 200 of those |
| §5.4 | `delete_runs` removes a run's forecasts before the run; `publish` also prunes forecasts outside the newest 5 servable runs (`active`, `superseded`, `building`) and those of rejected or failed runs |
| §8.6 gate | Besides the count check, a forecast carry-over check against the active run (new subsection above); `GATE_FORECAST_CARRYOVER = 0.5`. [2026-11-21 review] `footy publish` without `--run-id` refuses (exit 2) a newest `building` run that is not newer than the active run (a fit that was never published), so a night whose fit failed cannot bring older parameters back with a fresh `activated_at`; `--run-id` still publishes such a run on purpose |
| §8.7 scoring | A finished match whose score is not verified stays `pending` for 3 days after kickoff before it is voided `UNVERIFIED_RESULT` (an `AWARDED` match is still void at once) |
| §8.7 report | The omission rate counts omitted and published per processed upload |
| §6.5 `intake` (ADR-047) | The runtime validator is `intake/validate.ts`; `intake/schema.ts` (Zod) is used by the contract generator and the tests only, so Zod is not part of the Worker bundle |
| §9.2 alerts (Stage 7) | `raise_alert` still only records an `alert` event. `footy alert --flush` (the nightly's last step, `if: always()`) sends every undelivered alert event of the last 48 h (oldest first, in messages of at most 20 lines, `ALERT_MAX_LINES`; since PR 26 the source anomalies of one kind share one line with a count, "(27 fixtures in all)", and their events are marked delivered together) and sets `events.delivered_at` for the alerts a message showed (migration `0007`, additive) only after Telegram accepted it, so a failed send is retried; ingest's `warn` events `unmapped_team`, `canonical_update_needed` and `anomaly_*` count as alerts. `footy alert --text` (the `if: failure()` step) records the alert with a 24 h dedupe key and falls back to sending directly when the database is the problem |
| §9.2 health check (Stage 7) | `footy healthcheck` runs five checks (active run, run age against the run's own `stale_hours` as the Worker does, forecast coverage for today and tomorrow, stuck uploads, and any `bot_token_missing`, `alert_chat_invalid`, `alert_send_failed` or `watchdog_failed` event in the last 24 h), raises one deduplicated alert per failed check and exits 1 if any failed |
| §9.3 `nightly.yml` (Stage 7) | `ingest` (exit 3, a source outage, continues), `score`, `fit` (exit 4, a partial fit, continues to the gate), `publish`, `report --send --monday-only`, `healthcheck`, then the alert delivery. The football-data.org token reaches `ingest` only and Telegram reaches the report and alert steps only. The schedule does nothing until the repository variable `NIGHTLY_ENABLED` is `true` (first enablement after a green manual run) |
| §9.2 watchdog (Stage 7) | The Worker's cron trigger (`7 */6 * * *`) runs `watchdog/`: no active run, a run older than its stale limit (36 h by default), no forecast rows for today or tomorrow while `matches` has scheduled fixtures (the missing-forecast check of essentials 2), an upload `received` for over 10 minutes. Each finding is sent once per 24 h and recorded (key `alert:<name>`) only after Telegram accepted it. [2026-11-21 review] Once the stuck-upload alert was accepted, the watchdog closes those uploads as `failed` with `E_INTERNAL` (guarded by `status = 'received'`), so one silent upload (ADR-048) is reported once and no longer fails the watchdog and the nightly health check every day; if the alert could not be sent they stay `received`. With no bot token or no usable chat id it writes a `bot_token_missing` / `alert_chat_invalid` event instead, which the nightly health check reports. The chat id is read through `auth.alertChatId` (only `auth` reads the allowlist). The usage-hint path now also records `bot_token_missing` |

## 20. Version 3 (2026-11-21): read-only bot commands

The version-3 design is the changelog at the top, §1.4 (scope), §2 (FR-23 to FR-27, NFR-12), §5.7 (invariant 9), §6.2 to §6.6 (update kinds, behaviour matrix, outbound, modules, errors), §6.10 (the commands), §7.3, §7.6, §7.7 and §7.12 (diagrams, structure, flow), §8.12 (deep dive), §9 (threats S15 to S17, observability, deploy, tests, idempotency), §13 (rejections), §14 (ADR-049 to ADR-052) and §15 (R-P13, R-O8, R-M9).

What Divine decided on 2026-11-21: all ten commands (`/help` with `/start`, `/status`, `/fixtures`, `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team`, `/alerts`); `/fixtures` shows verdicts only; the commands that would change state (`/rerun`, `/rollback`, `/publish`, `/void`) are not built.

What stays as it is: the upload flow and its reply, the database schema (no migration), the Python CLI and the nightly job, the three auth layers and the `auth` module, the secrets (no new secret; `deploy.yml` reads the existing `TELEGRAM_CHAT_ID` for the menu scope), cost ($0).

Nothing in version 3 is deprecated or removed. Open items carried over unchanged: the `claude.md` in-place-edit wording, the missing design-rules file, git identity, Divine's GitHub billing check.

