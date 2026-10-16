nothing done yet still just started 

---

## 2026-10-16 — Pre-build documentation review (no code written)

- **Built against:** essentials file `system_architecture_essential_1.md`, architecture `system_architecture_1.md` (Derived From `PRD_1.md`)
- **Current stage:** none started. Next is Essentials 1, Stage 1 (Foundations and the Worker CPU spike)
- **Version alignment:** PRD_1, system_architecture_1 and essential_1 all carry N=1. Essentials `Source Architecture Version` matches the current architecture, and the architecture `Derived From` matches the current PRD, so no drift check is triggered.

### Module status
| Module | Status |
|---|---|
| Stage 1: Foundations and CPU spike | not started |
| Stage 2: Ingestion, aliases and bootstrap | not started |
| Stage 3: Dixon-Coles, backtest and metrics | not started |
| Stage 4: Pi-rating, bivariate Poisson, ensemble and publishing | not started |
| Stage 5: Telegram bot | not started |
| Stage 6: Scoring, calibration and weekly report | not started |
| Stage 7: Alerts, watchdog and go-live gates | not started |

### Done this session
- Read `claude.md`, the PRD, the full architecture and the essentials file.
- Renamed `prd_1.md` to `PRD_1.md` (by Divine) to match the `PRD_<digits>.md` rule in `claude.md`.

### Open issues
1. **Folder case:** the folder is now `PRD/` but `claude.md` and the architecture refer to `/prd/`. Rename the folder to `prd/` (preferred) or update `claude.md`. On Windows, `git mv` needs a two-step rename, and it matters on case-sensitive systems and CI.
2. **Uncommitted docs:** `claude.md`, `PRD/`, `system_architecture/`, `essentials/` and `tracker/` are untracked on `main`. They need a `feat/` branch and a pull request.
3. **Legal gate (blocks Stage 2):** `docs/legal/source_terms_register.md` does not exist. Source terms are unread. football-data.co.uk may forbid automated fetching. Divine must decide A-1 (use co.uk for nine-league history) or take the fallback.
4. **Open amendments A-1 to A-4** (architecture section 4.3, ADR log) still need Divine's decision. If accepted they need PRD_2 and system_architecture_2 from the System Designer.
5. **Team count:** architecture sizing says about 130 teams, but the canonical list has 179 (168 domestic plus 11 UCL-only). Fix in the next architecture snapshot.
6. **Missing rules file:** `SYETEM DESIGN RULES.html` is an empty shell (architecture section 16). Divine to supply the intended file if it exists.
7. **Git identity:** local git user is "BIKOIS_KITCHEN Developer" while the repo owner is DivineGima.
8. **Not yet created (Stage 1 work):** `pre-push` hook, `ci.yml`, `deploy.yml`, migrations, the app folders, `docs/verification.md`.

---

## 2026-10-16 — Engineering review of v1 plan (no code written)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md`. Review report: `/plan-eng-review`, 18 issues, 0 critical gaps, 10 decisions answered.
- **Current stage:** none started.

### TODO
- [x] **Carry the review's approved changes into the design documents (before Stage 1 coding).** DONE 2026-10-16: instead of new PRD_2 / architecture_2 / essentials_2 versions, Divine explicitly instructed that PRD_1, system_architecture_1, essentials_1 and this tracker be amended in place (see the next entry). Original wording of the changes: goals-only drift first with shots deferred until the co.uk decision (D3); each stage creates its own tables, minimal `0001` (D4); history-only club list `data/historical_teams.json` and Stage 2 counts (D5); source-rule checks during Stage 1 (D6); stuck-upload alert via `received` row plus watchdog (D7); void `NO_RESULT` 3 days after kickoff (D8); promotion gate = structural checks plus stability guard (D9); bootstrap through chunked bound-parameter requests, no SQL files (D10); UCL final treated like any match (D11); whole-nightly-job test on fake data (D12). Corrections: strip unknown keys not `.strict()`, full-precision `p_*` columns, CPU measured from Workers Logs `cpuTime`, private repos have no 60-day schedule auto-disable, 179 teams, "Stage" not "Phase", redundant `uploads` unique key, golden vectors compared by cell within 1e-9.
- [ ] **CPU fallback idea (only if the Stage 1 CPU spike p95 is above 6 ms):** consider having the nightly job pre-compute and store grids for the next 3 days of fixtures so the Worker only looks them up, as an alternative to ladder rungs F2/F3. Needs a PRD and architecture bump. Not built now.

### Still open (Divine's)
- A-1 (football-data.co.uk for history in all nine leagues, legal gate) and amendments A-2, A-3, A-4.

---

## 2026-10-16 — Source documents amended in place after the engineering review (no code written)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md`, all still N=1, so the version-alignment and drift checks in `claude.md` are unaffected. Divine explicitly authorised the in-place edits (an exception to the no-in-place-edit rule); changed passages are tagged `[Rev-1]`.
- **Current stage:** none started. Next is Essentials 1, Stage 1.

### What was changed (decisions D3 to D12, corrections C1 to C8)
| Ref | Change | Files |
|---|---|---|
| D3 | Drift is goals-only in v1; shots check and shots plumbing deferred until A-1 | PRD, architecture (ADR-026), essentials Stages 4-5 |
| D4 | Each stage creates its own tables; Stage 1 `0001` = `processed_updates`, `uploads`, `events`, `job_runs` | architecture (ADR-033), essentials Stages 1, 2, 4, 5, 6 |
| D5 | History-only clubs in `data/historical_teams.json`, `active=0` | PRD, architecture (ADR-027), essentials Stage 2 |
| D6 | Source-terms and free-history-depth checks done as notes during Stage 1 | PRD, architecture (ADR-032), essentials Stages 1-2 |
| D7 | `uploads` row written as `received` first; watchdog alerts if stuck over 10 minutes | PRD, architecture (ADR-029), essentials Stages 5, 7 |
| D8 | Pending predictions with no result 3 days after kickoff become void `NO_RESULT` | PRD, architecture (ADR-028), essentials Stage 6 |
| D9 | Promotion gate = structural checks + stability guard; no performance comparison | PRD, architecture (ADR-030), essentials Stage 4 |
| D10 | Bootstrap through chunked bound-parameter statements, no SQL files | architecture (ADR-031), essentials Stage 2 |
| D11 | UCL final treated like any match; no `NEUTRAL_VENUE` | PRD, architecture (ADR-034), essentials Stage 5 |
| D12 | Whole-nightly-job test on fake data in CI | PRD, architecture, essentials Stage 6 |
| C1-C8 | strip unknown keys; full-precision `p_*`; CPU from Workers Logs `cpuTime`; 60-day auto-disable is public-repo only; 179 teams; "Stage" not "Phase"; `update_id`-only unique key; golden vectors by cell within 1e-9 | architecture, essentials |

Full list: `system_architecture_1.md` section 18. Added test requirements: end of the essentials file.

### Module status
| Module | Status |
|---|---|
| Stage 1: Foundations and CPU spike | not started |
| Stage 2: Ingestion, aliases and bootstrap | not started |
| Stage 3: Dixon-Coles, backtest and metrics | not started |
| Stage 4: Pi-rating, bivariate Poisson, ensemble and publishing | not started |
| Stage 5: Telegram bot | not started |
| Stage 6: Scoring, calibration and weekly report | not started |
| Stage 7: Alerts, watchdog and go-live gates | not started |

### Open issues (updates to the 2026-10-16 pre-build entry)
1. Folder case: on disk the folder is now lowercase `prd/`, matching `claude.md` and the architecture. Resolved.
2. Uncommitted docs: still untracked on `main`; need a `feat/` branch and a pull request.
3. Legal gate and A-1: still Divine's decision. The terms and free-history-depth notes are now a Stage 1 task (D6).
4. Amendments A-1 to A-4: still open.
5. Team count: fixed in the architecture (179, plus about 60 history-only clubs). Resolved.
6. Missing rules file `SYETEM DESIGN RULES.html`: still open.
7. Git identity: still open.
8. Stage 1 work not yet created: `pre-push` hook, `ci.yml`, `deploy.yml`, minimal `0001` migration, app folders, `docs/verification.md`, `docs/legal/source_terms_register.md`.
9. New: `data/historical_teams.json` (about 60 clubs) has to be compiled before Stage 2 counts can pass.
10. New: the next `/plan-eng-review` run should re-check the amended documents; the earlier review log said "not CLEARED until the design versions are updated".

---

## 2026-10-16 — Divine's decisions on amendments A-1 to A-4 recorded (no code written)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1, amended in place, changes tagged `[Rev-2]`).
- **Current stage:** none started. Next is Essentials 1, Stage 1.

### Decisions
| Ref | Decision |
|---|---|
| A-1 | football-data.co.uk is never fetched automatically. **Path 1 (preferred):** if the Stage 1 terms check confirms that downloading its files by hand for personal use is allowed, Divine downloads them and loads them with the new `footy load-csv --dir <path>` command (run locally with the D1-only token; files never go in the repo); Scottish Premiership freshness = date of the last file loaded, weekly recommended. **Path 2 (fallback):** football-data.org only; the Scottish Premiership is dropped from v1 (SPL matches omitted as `INSUFFICIENT_HISTORY`; the screener prompt stops listing SPL); shots stay unused. Warm-up applies if the free football-data.org history is current-season only. |
| A-2 | Accepted: two Cloudflare tokens (nightly D1-only; deploy separate). |
| A-3 | Accepted: nightly cron `17 1 * * *` (01:17 UTC = 06:47 IST). |
| A-4 | Accepted: reply within 30 s of upload at p95 (NFR-11); this replaces the 15 s wording in the ADR section. |

Recorded as ADR-035 and ADR-036; NFR-11 added; PRD, architecture and essentials updated.

### Open issues
1. **Stage 1 terms check decides path 1 or path 2 of A-1** (does the site allow downloading its files by hand for personal use). The result goes into `docs/legal/source_terms_register.md`.
2. Uncommitted docs: still untracked on `main`; need a `feat/` branch and a pull request.
3. Missing rules file `SYETEM DESIGN RULES.html`: still open.
4. Git identity ("BIKOIS_KITCHEN Developer" vs repo owner DivineGima): still open.
5. `data/historical_teams.json` (about 60 clubs) must be compiled before the Stage 2 counts can pass.
6. `claude.md` still forbids in-place edits; no exception recorded there yet.
7. The next `/plan-eng-review` should re-check the amended documents.

---

## 2026-10-16 — Stage 1 built locally: Foundations and the Worker CPU spike (in-progress, not committed)

- **Built against:** essentials `system_architecture_essential_1.md` (Stage 1 only), architecture `system_architecture_1.md`, PRD `PRD_1.md`. All N=1, alignment and drift checks unchanged (still clean).
- **Branch:** `feat/stage-1-foundations`. Nothing is committed or pushed yet; no pull request exists. Stage 1 is **in-progress**, not complete, because its exit criteria need your Cloudflare and GitHub accounts (see "Needs Divine").

### Module status
| Module | Status |
|---|---|
| Stage 1: Foundations and CPU spike | **in-progress** (all locally verifiable work done; exit criteria blocked on Divine's account actions) |
| Stages 2 to 7 | not started |

### Stage 1 steps
| Step | State |
|---|---|
| 1 Repo skeleton (folders, lockfiles, Biome, strict tsc, ruff, mypy, `pre-push` hook) | done; hook installed here and tested against a real `git push` |
| 2 Verify-at-build notes (items 1 to 6) | done as notes: `docs/legal/source_terms_register.md`, `docs/verification.md`. No source fetched, all flags off |
| 3 Migration `0001` (`processed_updates`, `uploads`, `events`, `job_runs`) | done; applied to a local D1 with `wrangler` and tested on SQLite and Miniflare. **Not applied to a real D1 yet** |
| 4 Repo layers (TS `repo`, Python `d1_client.py`) + SQL-locality CI check | done; client has retry/backoff, chunking and resume, tested on a fake REST layer |
| 5 `auth` + webhook entry, dedupe, S1 to S3 | done; verified in Vitest and in a real `wrangler dev` run with curl |
| 6 CI workflows (`ci.yml`, `deploy.yml`), gitleaks, no-data check | written, YAML-validated, Actions pinned to SHAs. **Never run on GitHub** (no PR yet). Two Cloudflare tokens not created |
| 7 CPU spike | built and tested; **not deployed**, so no production `cpuTime` |
| 8 Decision gate | **open** |
| 9 Exit criteria | not met: CI not yet green on `main`, Worker not deployed, migration not on a real D1, no production CPU number |

### Tests (all green at the end of the session)
Vitest in workerd with local D1: 64. Node script tests: 41. pytest: 41. Biome, `tsc` (strict, bot and scripts), ruff, `mypy --strict`: clean. gitleaks on the tree: clean. Six hand mutations (auth compare, group chats, dedupe, parameter cap, retry of client errors, resume key) were each caught.

### Findings to act on
1. **CPU risk (indicative only):** the 60-match spike ran at a p50 of about 9 to 14 ms and p95 of 14 to 30 ms on this laptop in Node, noisy. Not the gate (the gate is production `cpuTime`), but the 6 ms target looks tight. Biggest costs: parsing three model blobs (about 2 ms) and Zod (about 0.8 ms), both addressed by F1. The grammY glue is not in the spike. Breakdown in `docs/verification.md` section 2. The parked "pre-computed grids" idea stays parked; it becomes relevant if production p95 is above 6 ms after F1.
2. **football-data.org free-history depth is still unknown** (no official statement; blog says current season only). Settling it needs one authenticated request, which the legal gate blocks until you sign. If current-season only, expect weeks of warm-up.
3. **A-1 evidence:** football-data.co.uk says its data is "for private individuals only" and "for the purposes of league match prediction only", and bars commercial or data-training use of automated bots/scrapers/AI. Manual download is not addressed. This supports path 1 but is not an explicit grant; the decision is yours (register section 2).
4. **Free-tier hard limits:** D1 Free daily row limits have been enforced since 2026-09-01 (queries fail until 00:00 UTC); Workers Logs keep only 3 days on Free, so measure `cpuTime` soon after the spike.
5. **Architecture inventory gaps (for the next snapshot, not edited here):** section 9.1 lists `TELEGRAM_WEBHOOK_SECRET` only as a Worker secret, but `set-webhook` needs it too; `WORKER_URL` is not listed. `deploy.yml` uses both as GitHub secrets.
6. **Package rename:** use `@cloudflare/vitest-plugin` (the `vitest-pool-workers` name is retired). Noted in `docs/verification.md`.
7. **`claude.md` still forbids in-place edits** and has no exception recorded for the earlier Rev-1/Rev-2 edits (unchanged open issue from before).

### Needs Divine (Stage 1 exit criteria)
Follow `docs/setup.md`: create the D1 database and commit its id; create the two Cloudflare tokens; create the Telegram bot and secrets; add the GitHub secrets; commit and push the branch and open the PR; merge once CI is green; then run the CPU gate and the D1 probe and fill in `docs/verification.md`. Also still open from before: the missing `SYETEM DESIGN RULES.html`, git identity, `data/historical_teams.json` (Stage 2), and the A-1 decision.

### Open issues
1. Stage 1 exit criteria (above).
2. Docs and code still untracked on `main`'s working tree; need the PR.
3. Legal register unsigned; A-1 path undecided.
4. `data/historical_teams.json` (about 60 clubs) must be compiled before Stage 2 counts can pass.
5. Missing rules file, git identity, `claude.md` in-place-edit exception.

### 2026-10-16 (later, same session) — Cloudflare work done through the connection
- Created D1 database `prob-bot` (id `f0d80197-890a-4009-8844-4d0fc82223f4`, account `d0a180c20666ef79ae23567c024d1a21`) and put the id in `apps/bot/wrangler.toml`. Workers subdomain `gimafolabit`, so the Worker URL will be `https://prob-bot.gimafolabit.workers.dev`.
- **Blocked, not worked around:** the connection cannot create API tokens (Cloudflare error 9109), and writing migration `0001` to the production D1 was denied by the permission check. `deploy.yml` applies it on the first merge; the remote database is still empty.
- `docs/setup.md` rewritten into ordered manual steps (C1 to C10) with links.

---

## 2026-10-16 (evening) — Stage 1 deployed; CPU gate measured and FAILED (in-progress)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1). Stage 1 is **in-progress**.
- **Done:** PR #1 merged and deployed (guard, migration `0001` on the real D1, Worker, webhook, smoke all green). PR #4 enabled the spike route; PR #5 fixed the measurement tooling (reads `wrangler tail` output, prime request, ignores stray requests). The merge permission rule for the GitHub tool was added locally (`.claude/settings.local.json`, not committed).
- **CPU gate (ADR-013):** three production runs, 73 spike requests read from Workers Logs: p50 6 ms, **p95 22 ms**, max 63 ms; 16 of 73 at or above the 10 ms Free limit; the first requests on a fresh isolate cost 22 to 63 ms. Nothing failed (Cloudflare tolerates occasional overruns) but the 6 ms target is missed by a wide margin. Full table: `docs/verification.md` section 2.
- **Next (essentials step 8):** apply F1 (per-team rows instead of whole blobs, hand validator instead of Zod, precomputed tables), re-measure, and report. Do not adopt F2/F3 without Divine.
- **For Divine (parked idea, now relevant):** have the nightly job pre-compute and store each match's grid for the next 3 days of fixtures, so the Worker only looks them up and the TypeScript grid port disappears. It needs a PRD and architecture version bump, so it is not built. It becomes the leading option if the F1 re-measure still misses 6 ms.
- **Process notes:** `wrangler tail` is lossy (about 65% of events), so the Workers Logs query is the measurement source from now on. The spike route (`SPIKE_ENABLED=1`) stays on for the F1 re-measure and must be switched back to `0` afterwards.

### Module status
| Module | Status |
|---|---|
| Stage 1: Foundations and CPU spike | **in-progress** (deployed; CPU gate failed, F1 re-measure pending) |
| Stages 2 to 7 | not started |

### Open issues
1. CPU gate (above). 2. Live D1 probe (verify item 3) not yet run (needs the nightly token and a shell). 3. Legal register unsigned; A-1 undecided. 4. `data/historical_teams.json` for Stage 2. 5. Missing rules file, git identity, `claude.md` in-place-edit exception.
