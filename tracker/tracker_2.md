# Tracker, version 2 (PRD_2, system_architecture_2, essential_2)

> Trackers follow the version number N (claude.md §5): tracker_1 = version 1, tracker_2 = version 2, tracker_3 = version 3, tracker_4 = version 4. Entries were split out of `tracker_1.md` on 2026-11-21 word for word; nothing was reworded.

## 2026-10-17 (night) - Version 2 written; Stages 5a, 5b and 6 built (code complete; live verification pending)

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` (all N=2; alignment and drift checks clean). Branch `feat/stage-5-6-forecasts`, from `main` after PR #20.
- **Why version 2 (Divine's decision of 2026-10-16, ADR-037, made a design on 2026-10-17 with Divine's authorisation):** the Worker CPU gate failed (p95 16 ms after the trims against a 6 ms target), so the nightly job now computes and stores one forecast per scheduled fixture and the Worker only looks it up. Numbered **2, not 3**, because `claude.md` requires PRD, architecture and essentials to share N with no gaps; renaming is trivial if Divine wants another number. **Essentials 1 Stages 5 and 7 are superseded and Stage 6 re-specified by essentials 2** (Rev-5 notes in essentials 1); for the read order, essentials 1 has no remaining incomplete stage (Stages 1 to 4 complete, 5 to 7 superseded).
- **Done (tests green: 548 pytest, 212 Vitest, 50 script tests; ruff, mypy strict, tsc, Biome on changed files, repo rule checks, migration lint):**
  1. Documents: PRD_2 (changelog, decisions 27 to 29), architecture 2 (changelog with Downstream Impact, `fixture_forecasts`, section 8.11, ADR-042 to ADR-046, as-built 19.1), essentials 2 (Stages 5a, 5b, 6, 7 changes).
  2. **Stage 5a (Python):** `footy/drift.py`, migration `0004`, `footy/forecast`, `ForecastRepo`; `fit` writes the forecasts and records `n_forecast_fixtures`; the promotion gate requires them; `publish` prunes forecasts beyond 5 runs; rollback warns when a run has none.
  3. **Stage 5b (Worker):** Zod contract + generated `packages/contracts/screener_v1.schema.json` (drift test), intake guards, plain-`fetch` Telegram client (no grammY, ADR-043), forecast/prediction/team repos, migration `0005` (`predictions`, `omissions`), upload pipeline (`received` row first, copy of the stored forecast, first prediction wins, persist then reply), reply formatter with IST `+1d` and splitting, usage hint, stale/model/no-forecast banners; bot token readable only in `telegram/` (repo check extended).
  4. **Stage 6 (Python):** `footy score` (scored / void by reason / `NO_RESULT` after 3 days, idempotent, one alert), rolling per-model RPS feeding `fit` (alignment rule), `footy report` (metrics, paired bootstrap interval, honest wording, matplotlib chart, `calibration_snapshots` via migration `0006`, Telegram sender), backtest regression check, `data.yml` (`score`, `report`), `backtest.yml`, whole-nightly-job test, `matplotlib` pinned with hashes.
- **Hand mutations (33 over the three stages, each caught).** One mutation (moving the `uploads` insert after the download) could not be expressed as a single text edit; that rule is covered by the killed-Worker test instead.
- **Findings while building:** (a) `INSERT OR IGNORE` also skips rows that break a CHECK instead of raising (documented, covered by tests; the pipeline fails loudly if a row cannot be read back). (b) the exclusion-gate regex `` missed `G2_EARLY_SEASON` (underscore is a word character); caught by a test, fixed. (c) `predictions.run_id` has no foreign key (ADR-045), otherwise pruning old runs would fail on logged predictions. (d) An immutability trigger on `predictions` was written and then removed: the architecture asks for the invariant to be enforced in code and tests, and a trigger body in a migration is a deploy risk that cannot be repaired after merge (merged migrations are immutable); tests pin that only the result columns are ever written.
- **Not verifiable here (needs Divine and production), tracked as in-progress:**
  1. Merge, then the deploy applies migrations 0004 to 0006.
  2. Add the Worker secret `TELEGRAM_BOT_TOKEN` and the GitHub secret `TELEGRAM_CHAT_ID`.
  3. Run `fit` and `publish` from Actions. **Until then the active run has no forecasts and every match would be `NO_FORECAST`.**
  4. A real upload, then the Stage 5b CPU gate (p95 on 15, 60 and 100 matches, target 6 ms) and the 30 s reply target; the live `json_each` insert; `score`; `report --send`; the first `backtest.yml` run. Checklist: `docs/setup.md` C13 and `docs/verification.md` section 7.
- **Carried forward (unchanged):** the `claude.md` in-place-edit wording (it has no recorded exception for Rev-1 to Rev-4 or for the version files written at Divine's instruction), the missing `SYETEM DESIGN RULES.html`, git identity, live `d1-probe`. New: Stage 7 gains a watchdog check for missing forecasts (essentials 2).

### Module status
| Module | Status |
|---|---|
| Stages 1 to 4 | **complete** |
| Stage 5a: nightly forecasts (Python) | code **complete**; first live `fit` + `publish` **in-progress** |
| Stage 5b: Telegram bot | code **complete**; real upload, CPU gate and reply-time check **in-progress** |
| Stage 6: scoring, calibration, weekly report | code **complete**; first scored predictions and a delivered report **in-progress** |
| Stage 7: alerts, watchdog, schedule, go-live | not started (essentials 2 Stage 7) |

---

## 2026-10-17 (night, later) - Code review of Stages 5a, 5b and 6 (PR 21); findings repaired; source of truth re-aligned

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` (all N=2). Branch `feat/stage-5-6-forecasts`, PR 21.
- **Review:** `/code-review` at high effort over PR 21: 9 findings. Each was checked against the code before acting. **7 real and fixed, 1 not a defect, 1 real but outside this PR (recorded, not changed).** Tests: 564 pytest, 216 Vitest, 50 script tests; ruff, mypy strict, tsc, Biome on changed files, repo rule checks and migration lint clean; 7 further hand mutations of the fixes, each caught.

| # | Where | Problem | Why it matters | Fix |
|---|---|---|---|---|
| 1 | `score/settle.py` | A finished match with an unverified score was voided `UNVERIFIED_RESULT` at first sight | Reconcile lets `unverified` become `regular` or `ft_90` later, but the void is final (updates are guarded by `status = 'pending'`), so a scoreable prediction was lost from the 300-match sample | It now waits the same 3 days as a missing result, then voids; an `AWARDED` match is still void at once. Tests: waits, scores once verified, voids after the window |
| 2 | Worker `repo` | `INSERT OR IGNORE` also skips rows that break a CHECK or NOT NULL; the upload was finalised `processed` and then the read-back failed | A bad row gave an error reply for an upload the log called processed, and the watchdog could not see it | `INSERT ... ON CONFLICT (fixture_key) DO NOTHING`: only the key clash is ignored, a bad row raises, the batch (predictions, omissions, upload close) rolls back and the upload stays `received`. Omissions use a plain `INSERT`. Tests for both |
| 3 | `repo/forecasts.py` | `prune` counted failed, rejected and building runs among the newest 5 | After a few bad nights the rollback target lost its forecasts | Slots go to `active`, `superseded` and `building` runs only; rejected and failed runs lose theirs. Test with two dead runs |
| 4 | `repo/predictions.py` | Omissions were counted per upload but published predictions once per fixture | Each re-upload of the same file raised the omission rate in the weekly report | Both sides are counted per processed upload, so a re-upload leaves the rate unchanged. Test |
| 5 | `system_architecture_1.md` | Reported as edited in place | Would break the "never edit a prior version" rule | **Not a defect:** the file has no diff in this PR (checked with `git diff origin/main`). Essentials 1 did get the Rev-5 supersession notes, as recorded |
| 6 | `backtest/job.py` `_memoised` | The pi-rating cache key lists the config fields it reads by hand | A future field change could silently reuse a fit in a sweep | **Pre-existing code (PR 20), not touched by this work. Not changed here.** Follow-up: fit the pi-rating once outside the sweep loop, or let the fitter declare its fields |
| 7 | Worker `repo` | `insertManyIgnoreDuplicates` and `commit` built the same insert twice; the active-run SELECT and its mapping appeared twice | Two paths could drift apart; tests exercised the one production does not use | One `predictionStatement` helper, one `POINTER_SQL` and `toPointer`; the method stays because the architecture names it and tests now cover the `commit` path |
| 8 | `publish/gate.py` | A run with zero forecasts passed the count check and could replace a run that still served the next days | A fit that found no fixtures (ingest not yet run, a feed gap) silenced the bot until the next fit | New carry-over check: the new run must forecast at least 50% of the fixtures the active run forecasts for the new run's start date or later (`GATE_FORECAST_CARRYOVER`, unvalidated); skipped by `--accept-drift` |
| 9 | Worker `upload` | A second listing of an already-logged fixture fell through to the time checks | It could be reported as `STARTED` or `TOO_FAR` instead of a duplicate | The repeat is `DUPLICATE_PAIR`. Also: a repeated `match_id` now takes the next free numbered label, never one that exists in the file, so an omission row is never lost |

- **Source-of-truth alignment (after the review, compared with the code):**
  - `system_architecture_2.md` **corrected**: section 3.3, 5.4, 8.6 (carry-over subsection), 8.7 (conflict-only insert, unverified wait, per-upload omission rate), 8.11 (which runs keep forecasts), 9.5 and 9.6 (insert wording), and the as-built table 19.1.
  - `system_architecture_essential_2.md` **corrected**: Stage 5a step 5 (pruning and carry-over), Stage 5b step 5 (the insert), Stage 6 steps 1 and 4.
  - `PRD_2.md` **not touched**: no requirement changed or was contradicted. `PRD_1.md`, `system_architecture_1.md`, `essential_1.md` not touched.
- **Still open (unchanged):** the live checks listed in the previous entry (secret, `fit` + `publish`, a real upload, CPU gate, `report`), and: the `claude.md` in-place-edit wording, the missing `SYETEM DESIGN RULES.html`, git identity, live `d1-probe`. New follow-up: the pi-rating memoisation key (finding 6).

### Module status
| Module | Status |
|---|---|
| Stages 1 to 4 | **complete** |
| Stage 5a, 5b, 6 | code **complete and reviewed**; live verification **in-progress** (needs Divine) |
| Stage 7 | not started |

---

## 2026-10-18 - First live run of Stages 5a, 5b and 6 (go-live checks 1 to 4); the CPU target is missed

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` (all N=2). No source file changed; this entry and `docs/verification.md` section 7 record what the live service did. Branch `docs/stage-5-6-live-verification`.
- **Done by Divine, in order:** the deploy of PR 21 (migrations 0004 to 0006 applied, Worker deployed, webhook registered, smoke green); `wrangler secret put TELEGRAM_BOT_TOKEN`; `ingest`-fed `fit` (run 39072264066) and `publish` (run 39072948642); real uploads to the bot.
- **What worked live:**
  - `fit` stored **49 forecasts** (30 `ok`, 11 `DRIFT`, 8 `INSUFFICIENT_HISTORY`); `publish` **promoted** run `R20261017T214541Z` (gate passed, 49 forecast rows of 49 expected).
  - The bot answers: a text gets the usage hint; a file with too long `notes` is rejected with `notes (too_big)` and nothing is computed; a file with no matches gets `File valid: 0 matches passed`; a file with 7 real fixtures gets 5 probability blocks and 2 omissions with the right reasons (`DRIFT`, `INSUFFICIENT_HISTORY`).
  - **The live `INSERT ... json_each ... ON CONFLICT DO NOTHING` works:** 16 predictions logged from 3 files, all `pending`, one per fixture key; every re-upload reported all as already logged. Reply time 0.9 to 1.6 s (target 30 s).
- **Found live, not by tests:** the first token entered was rejected by the Worker's format check, so every update ended `no_telegram_client` (no reply, no crash, as designed). Re-entering the token fixed it. The reply when the token is bad is silence; the Stage 7 watchdog should alert on a `bot_token_missing` event (the Worker already writes it for uploads, not for the usage hint). Also: the screener writes its own exclusion names (`ROTATION_RISK`, `EARLY_SEASON`), so the bot counts them as `OTHER`; it expects `G1` to `G6` codes. Both noted below.
- **CPU target missed (check 1).** Warmed uploads of 15 and 49 matches cost **7 to 9 ms** of Worker CPU (p50 8); the first request after a quiet period cost **11 to 25 ms**; 5 of 13 requests were at or above the 10 ms Free-plan limit and none failed. The cost does not grow with the file, so it is fixed work (parse, Zod, SHA-256, the Telegram calls, D1 calls), not model arithmetic. Not measured: 60 and 100 matches (only 49 forecasts exist) and a large sample. Full table in `docs/verification.md` section 7. **Decision needed from Divine** (CLAUDE.md: escalate): F1 trim of validation (hand validator instead of Zod, then re-measure), accept as a recorded exception, or a paid plan. Nothing adopted yet.
- **Test data in the live log:** 16 of the logged predictions came from test files Claude Code built from the stored fixtures (not screener output). They are real forecasts of real fixtures and will be scored and counted in the weekly report. Divine decides whether to keep them or to delete the 16 rows.
- **Not yet verified:** `score` on played matches, `report --send` (needs the `TELEGRAM_CHAT_ID` GitHub secret), the first scheduled `backtest.yml` run, the first scored predictions.
- **Source of truth:** compared after the live run; the design did not change, so `PRD_2`, `system_architecture_2` and `essentials_2` are **not touched**. If Divine picks the F1 trim or a plan change, architecture section 8.10 / ADR-013 and risk R-P1 get updated in that change.
- **Still open (unchanged):** the `claude.md` in-place-edit wording, the missing `SYETEM DESIGN RULES.html`, git identity, live `d1-probe`, the pi-rating memoisation key follow-up. Stage 7 not started (new: a watchdog check for a missing bot token and for missing forecasts).

### Module status
| Module | Status |
|---|---|
| Stages 1 to 4 | **complete** |
| Stage 5a: nightly forecasts | **complete** (live `fit` + `publish` done, 49 forecasts) |
| Stage 5b: Telegram bot | working live; **CPU gate missed, decision pending**; reply time met |
| Stage 6: scoring, calibration, weekly report | code complete; `score`, `report --send` and first backtest run **in-progress** (need played matches and `TELEGRAM_CHAT_ID`) |
| Stage 7: alerts, watchdog, schedule, go-live | not started |

---

## 2026-10-18 (later) - F1 trim of the screener validation (CPU gate, ADR-047)

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` (all N=2). Branch `fix/worker-hand-validator`. Divine chose "trim first, then Stage 7" after the CPU miss recorded in the entry above.
- **What changed:** the Worker no longer runs Zod. `apps/bot/src/intake/validate.ts` is a hand validator for the screener file; `intake/index.ts` calls it. `intake/schema.ts` (Zod) is unchanged and still produces the JSON Schema and the contract drift test, so the contract has one source. Zod is no longer in the Worker bundle (bundle 70 KB, no Zod code).
- **How it is kept equal to the contract:** `test/intake-validate.test.ts` feeds the Zod schema and the hand validator 6,000 mutated files (one to three random edits of a valid file, 55 replacement values plus deletions) and requires the same verdict, the same set of `path (code)` issues and the same parsed data (unknown keys dropped); it also checks the 100-match and 200-excluded caps. Run ad hoc with three other seeds and 30,000 cases each (90,000): no difference. Two Zod quirks had to be copied (the length limits apply to a wrong-typed value that has a length; an oversize array reports only `too_big`, no element issues).
- **Tests:** Worker 220 (was 216), script tests 50, `tsc`, Biome on the changed files, SQL-locality and secret-reader checks clean. Python untouched.
- **Source of truth:** `system_architecture_2.md` corrected (section 6.5 interface and component, error catalogue wording, section 8.10 note, ADR-047 in the index and the decision log, as-built table); `essentials_2.md` Stage 5b steps 2 and 3 corrected. `PRD_2.md` not touched (it says files are validated before any computation, which is still true; it names Zod as a tool, which remains the contract tool).
- **Not verified yet:** the effect on CPU. After the merge deploys, Divine repeats the uploads (15-match and 49-match files, four sends each, plus one after a quiet spell) and Claude Code records the new numbers in `docs/verification.md` section 7. If warmed p95 is still above 6 ms, escalate to Divine again (architecture section 8.10).
- **Still open (unchanged):** `TELEGRAM_CHAT_ID` secret, `score` and `report` on played matches, first `backtest.yml` run, decision on the 16 test predictions, the `claude.md` in-place-edit wording, the missing `SYETEM DESIGN RULES.html`, git identity, live `d1-probe`, the pi-rating memoisation follow-up. Stage 7 not started.

### Module status
| Module | Status |
|---|---|
| Stages 1 to 4 | **complete** |
| Stage 5a | **complete** |
| Stage 5b | working live; CPU trim **code complete, awaiting re-measurement** |
| Stage 6 | code complete; live checks **in-progress** |
| Stage 7 | not started |

---

## 2026-10-18 (last) - CPU gate re-measured after the F1 trim; miss accepted by Divine (ADR-048); go to Stage 7

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` (all N=2). Branch `docs/cpu-gate-decision`. No code changed.
- **Merged since the previous entries:** PR 22 (live-run record) and PR 23 (hand validator in place of Zod, ADR-047; deploy green).
- **Re-measurement (version `2a068cd6`, 13 requests, 15- and 49-match files):** warmed (11 samples) **5 to 8 ms, median 7**; first request of a burst 17 and 14 ms; handler time 0.9 to 1.1 s. Before the trim: warmed 7 to 9 ms (median 8), first request 11 to 25 ms. The 6 ms target is **not met**; no request failed in 26 production requests, 7 of which were at or above the 10 ms Free-plan limit (all first requests after a quiet spell). Table in `docs/verification.md` section 7.
- **Decision (Divine, asked with the risk explained):** accept the miss and proceed to Stage 7. Considered and not chosen: the paid Workers plan (a new architecture version) and more trims (about 1 ms, uncertain). Worst case if Cloudflare ever enforces the limit strictly on a cold request: a silent upload that is sent again; the insert is all-or-nothing, a repeat is reported as already logged, nothing is lost or wrong.
- **Source of truth:** `system_architecture_2.md` corrected (ADR-048 in the index and the decision log, a note in section 8.10, risk R-P1 re-rated Medium / Low); `essentials_2.md` and `PRD_2.md` not touched (no requirement or step changed).
- **Carried into Stage 7:** a watchdog check for an upload stuck in `received` (silent upload), for missing forecasts and for a missing bot token (a bad token gives silence; found live on 2026-10-18).
- **Still open:** `TELEGRAM_CHAT_ID` secret; `score` and `report --send` on played matches; first scheduled `backtest.yml` run; what to do with the 16 test predictions; screener exclusion names (`G1` to `G6`); the `claude.md` in-place-edit wording; the missing `SYETEM DESIGN RULES.html`; git identity; live `d1-probe`; the pi-rating memoisation follow-up.

### Module status
| Module | Status |
|---|---|
| Stages 1 to 4 | **complete** |
| Stage 5a | **complete** |
| Stage 5b | **complete** (CPU target missed, accepted, ADR-048) |
| Stage 6 | code complete; live checks (`score`, `report`) **in-progress** |
| Stage 7: alerts, watchdog, schedule, go-live | **next** (not started) |

---

## 2026-10-18 (Stage 7) - Alerts, health check, nightly schedule, watchdog, backup, runbook (code complete, not yet merged)

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` Stage 7 (all N=2). Branch `feat/stage-7-alerts-watchdog`; not committed, no PR yet (Divine asked to wait).
- **Python:** migration `0007_event_delivery.sql` (`events.delivered_at`, additive); `alerts/catalogue.py` (wording), `alerts/deliver.py` (`flush_alerts`, `alert_with_text`); `health.py` and `repo/health.py` (five checks); `footy healthcheck` and `footy alert --flush|--text`; `OpsRepo.pending_alerts` and `mark_delivered`; config constants. Ingest's `warn` events (unmapped team, canonical update, anomalies) are delivered as alerts without touching ingest.
- **Workflows:** `nightly.yml` (cron `17 1 * * *`, off until variable `NIGHTLY_ENABLED` is `true`, 45 min, concurrency shared with `data.yml`, least-privilege secrets per step, `if: always()` alert delivery and `if: failure()` failure alert) and `backup.yml` (weekly `wrangler d1 export`, checked, 30-day artifact; `upload-artifact` pinned to `cf430e03...` v7.0.2).
- **Worker:** `watchdog/` (no run, stale run, missing forecasts, stuck upload; once per 24 h per finding; recorded only after Telegram accepted), `scheduled` handler, cron `7 */6 * * *` in `wrangler.toml`, `auth.alertChatId`, `HealthRepository.forecastCoverage`, `EventRepository.hasRecent`; the usage-hint path now records `bot_token_missing` (found live: a bad token was silent).
- **Docs:** `docs/runbook.md` (daily ritual, alert table, rollback, rotation, restore drill, auto-disable check, go-live checklist). Architecture 2 (section 9.3 backup row, as-built rows) and essentials 2 (Stage 7 as-built) corrected; PRD_2 untouched.
- **Tests:** Python 601 (was 564 + 37 new), Worker 238 (was 220 + 18 new), script tests 50; ruff, mypy strict, tsc, SQL-locality, secret-reader, migration lint clean.
- **Verified live: nothing yet.** After merge and deploy: the migration applies; the cron trigger registers; a manual `nightly` run; a manual `backup` run (the D1 token must be allowed to export: first run proves it); an alert actually arriving; set `NIGHTLY_ENABLED`; seven green nights; the drills in the runbook.
- **Still open:** the items of the earlier entries (secret `TELEGRAM_CHAT_ID`, `score` and `report` on played matches, first `backtest.yml`, the 16 test predictions, screener gate codes, `claude.md` wording, missing design-rules file, git identity, `d1-probe`, pi-rating memo follow-up).

### Module status
| Module | Status |
|---|---|
| Stages 1 to 6 | **complete** (live checks of Stage 6 pending) |
| Stage 7 | code **complete**; live proof and go-live checklist **in-progress** (Divine) |

---

## 2026-10-18 (Stage 7 review) - Code review of Stage 7; findings repaired; source of truth re-aligned

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` Stage 7 (all N=2). Branch `feat/stage-7-alerts-watchdog`.
- **Review:** `/code-review` at high effort: 10 findings. Each was checked against the code before acting: **8 real and fixed, 1 dead code removed, 1 not a defect.** Tests now: Python 605, Worker 238, script tests 50; ruff, mypy strict, tsc and the repo rule checks clean.

| # | Where | Problem | Why it matters | Fix |
|---|---|---|---|---|
| 1 | `health.py` | The `bot_token` check counted only `bot_token_missing` | A token Telegram refuses, a bad chat id or a watchdog crash left the Worker unable to alert and nothing told anyone (NFR-08) | It counts `bot_token_missing`, `alert_chat_invalid`, `alert_send_failed` and `watchdog_failed`. Test per kind |
| 2 | migration `0007` | A partial index on `delivered_at IS NULL` | Almost every event stays NULL, so the index was the whole table and the delivery query could scan 90 days of events | No index: the 48 h window uses `idx_events_at` |
| 3 | `nightly.yml` | An unhealthy night also fired the generic "nightly failed" alert | One fault gave several messages a night | The failure step skips when the health step is the failed one; its own alert explains it |
| 4 | `health.py` | The token report looked back 48 h with no "fixed since" | The check stayed red for two nights after the fix | Look back 24 h; documented in the runbook |
| 5 | `backup.yml` | Own concurrency group; D1 export blocks the database | The Sunday export could overlap a nightly or an upload | Same group as the data runs (`footy-data`) |
| 6 | `alerts/deliver.py` | `alert_with_text` re-sent directly after any exception, including a failed "mark delivered" after Telegram had accepted | The same alert twice, a third time at the next flush | Only a failed recording falls back to a direct send; a failure after recording leaves the alert pending. Test |
| 7 | `alerts/deliver.py` | All pending alerts were marked delivered although only the first 20 were shown | The rest were lost ("and N more") | Sent in messages of 20, each marked after its own send. Tests, including a failure on the second message |
| 8 | `health.py` | The nightly check used the constant 36 h; the Worker uses the run's `stale_hours` | Two checks disagreed about when a run is stale | The nightly check reads the run's own limit. Test |
| 9 | `repo/health.py` | `last_finished_job` was never used | Dead code that looked like a job-freshness check | Removed |
| 10 | watchdog and health | A day with scheduled fixtures and no forecast rows could mean "no team can be forecast" | **Not a defect:** the fit writes a row for every scheduled fixture in the window, with verdict `NO_MODEL` or `INSUFFICIENT_HISTORY` when it cannot forecast, so zero rows on a day with fixtures means the job did not cover it | None |

- **Source of truth:** `system_architecture_2.md` (health-check and delivery as-built rows) and `docs/runbook.md` corrected to match the fixes. Essentials 2 and PRD_2 needed no change.
- **Still open:** the live proof list of the previous Stage 7 entry; the earlier open items.

---

## 2026-10-18 (first live nightly run) - Stage 7 proven on production; anomaly alerts grouped

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` Stage 7 (all N=2). Branch `fix/group-anomaly-alerts`.
- **Live result (manual run of `nightly`, run 39083505527, 2 min 48 s, every step green, failure alert skipped as designed):** ingest ok (123 matches unchanged), score (16 pending, none played yet), fit (49 forecasts, all three models ok), publish promoted (carry-over 49 of 49), Monday report skipped (not a Monday), health check healthy (all five checks ok), alert delivery sent 42 alerts in 3 messages. Migration `0007` and the cron `7 */6 * * *` deployed with PR 25.
- **Found live:** all 42 alerts were `anomaly_status_regression` (27 fixtures that the feed reports going from FINISHED back to TIMED), one line each, and each would come back every night when the 24 h dedupe lapses. `flush_alerts` now sends source anomalies of one kind as one line with a count ("(27 fixtures in all)"); the events are marked delivered together. Test added; Python 606 tests, ruff, mypy strict (src and tests) clean.
- **Open:** whether the 27 status regressions are a real feed problem (they were first seen on 2026-10-16); `backup` first run; `NIGHTLY_ENABLED`; seven green nights; the drills; the earlier open items.

---

## 2026-10-18 (backup and restore drill) - Backup proven; restore drill passed

- **Backup:** manual run of `backup` (run 39084262728) green in 27 s; export 4.6 MB, so the nightly D1 token is allowed to export; artifact `prob-bot-d1-export` kept 30 days.
- **Restore drill (done by Claude Code with Divine's go-ahead):** downloaded that artifact, created the scratch database `prob-bot-restore-test`, loaded `prob-bot.sql` into it (81,591 rows written, 18 tables) and compared it with the live database: matches 9,280, teams 238, predictions 16, forecasts 98, model runs 4, events 42, migrations 7, and the same active run (`R20261018T004052Z`) in both. The scratch database and the downloaded file were then deleted. The live database was only read.
- **Go-live checklist (docs/runbook.md section 8):** done: nightly run by hand green, backup run by hand green, restore drill. Still Divine's: set variable `NIGHTLY_ENABLED` to `true` (Settings, Secrets and variables, Actions, tab Variables), seven green nights, a real upload with `score` and the weekly `report` seen once, the decision on the 16 test predictions, the token-rotation drill.

---

## 2026-11-21 - Why the workflows failed (Oct 25 - Nov 20); CI time-bomb test fixed

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` Stage 7 (all N=2). Branch `fix/alert-flush-test-clock`. Test-only change; no production code, schema or workflow touched.
- **Finding 1 (not code): Actions blocked by GitHub billing, 2026-10-25 to 2026-10-31.** Seven `nightly` runs and the 2026-10-25 `backup` ended in 2 s with no step run; the run annotation reads "The job was not started because recent account payments have failed or your spending limit needs to be increased". The active run aged past the 36 h limit, so the bot showed STALE MODELS. Cleared on 2026-11-01 (new billing month). This repo used about 90 Actions minutes in October, so the limit was spent account-wide or a payment failed. Divine to check Settings, Billing and plans. It can recur at any month's end.
- **Finding 2 (fixed): every Dependabot PR (#29 - #38) failed CI since 2026-11-01** on `test_alert_flush_sends_the_pending_alerts_once`. The test stamped its alert `2026-10-18T01:00:00Z`, but `alert --flush` reads the real clock (`cli.py`) and sends only alerts from the last `ALERT_FLUSH_HOURS` (48 h), so from 2026-10-20 the alert was "stale" and the test failed. The test now stamps the alert with `footy.clock.utc_now()`. Production behaviour was correct throughout.
- **Health:** `nightly` green every day 2026-11-01 to 2026-11-20 (ingest, fit with all three models, gate passed, promoted, health check healthy).
- **Checks:** Python 606 tests pass, ruff and mypy clean.
- **Module status:** alerts `complete` (unchanged); CI `complete`.
- **Open:** Divine's billing check; rebase and review the ten Dependabot PRs; the earlier open items.

---

## 2026-11-21 (code review) - Whole-project review: two fixes, one doc correction

- **Built against:** `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` Stage 7 (all N=2). Branch `fix/review-2026-11-21`.
- **Review:** `/code-review` (high) over the whole project, then every finding checked by hand against the code, the architecture and this tracker. The probability code was also read line by line: Dixon-Coles tau and its gradients, the bivariate Poisson convolution, the pi-rating update (Constantinou and Fenton 2013) and its scale fit, the over lines and total-goals pmf, the ensemble softmax and shrinkage with the aligned RPS history, and RPS with the 1/(r-1) normalisation. **No error found; nothing changed there.** No security or duplication finding.
- **Fixed 1 (watchdog):** an upload stuck in `received` was never closed, so the watchdog alerted every day and the nightly health check failed every night until the row was fixed by hand. After its alert is accepted, the watchdog now closes those uploads as `failed` (`E_INTERNAL`); if the alert cannot be sent they stay open. Tests in `apps/bot/test/watchdog.test.ts` (shown to fail without the fix).
- **Fixed 2 (publish):** `footy publish` without `--run-id` took the newest `building` run of any age. The 2026-11-20 nightly left one unpublished `building` run. On a night when every model fails, a leftover run 1 to 3 days old could pass the carry-over gate and go live with a fresh `activated_at`. Publish now refuses (exit 2) a `building` run that is not newer than the active run; `--run-id` still publishes it on purpose. Test in `apps/fit/tests/test_fit_publish.py` (shown to fail without the fix: the older run was promoted).
- **Doc drift corrected:** architecture §9.2 alerts row said "messages of at most 20 alerts"; since PR 26 the limit is 20 lines and anomalies of one kind share a counted line. The `ALERT_MAX_LINES` comment said the rest are "counted, not listed"; they are sent in further messages. The §8.6 gate row, the §9.2 watchdog row and `docs/runbook.md` now describe fixes 1 and 2.
- **Dismissed after checking (no change):** ingest exit 2 stopping the nightly (documented fail-closed, §9.3); the ignored `commit()` result (unreachable: one row per deduplicated update); the health check counting `alert_send_failed` (intentional, Stage 7 review item 1); the single Telegram retry (documented, §8); forecast horizon 4 versus ingest 3 (documented: the extra days cover a late nightly).
- **Missing fields of earlier entries (append-only, so recorded here):** "2026-10-18 (first live nightly run)": module status alerts `complete`, nightly workflow `complete`. "2026-10-18 (backup and restore drill)": built against `PRD_2.md`, `system_architecture_2.md`, `system_architecture_essential_2.md` Stage 7; module status backup `complete`, restore drill `complete`.
- **Module status:** watchdog `complete`; publish `complete`; alerts `complete` (unchanged).
- **Open:** Dependabot PR #35 (@cloudflare/vitest-plugin) waits for a rebase; local `biome check` on Windows reports CRLF line endings (CI on Linux is clean); Divine's GitHub billing check; the earlier open items.

---
