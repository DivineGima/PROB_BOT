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

---

## 2026-10-16 (night) — F1 applied and re-measured; CPU gate still FAILS, decision handed to Divine (in-progress)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1). Stage 1 is **in-progress**.
- **Done:** PR #7 applied the F1 trims (hand validator instead of Zod, per-team model rows, Poisson recurrence) and was deployed as Worker version bd061009. Outputs are unchanged (regression tests pin the old results; 1,500-payload validator equivalence test).
- **CPU gate after F1** (production, Workers Logs, 39 spike requests, all 200): p50 3 ms (was 6), **p95 16 ms** (was 22), max 22 ms (was 63); 4 of 39 at or above 10 ms (was 22% of requests). Without the first five requests p95 is 6 ms but one request still took 16 ms. The first requests of a fresh isolate cost 22, 13, 9, 4, 12 ms. Table and series: `docs/verification.md` section 2.
- **Verdict:** the gate (p95 at most 6 ms, nothing near 10 ms) is not met. F1 is exhausted. Because uploads arrive about once a day, nearly every real upload will be a cold-isolate request, and the spike still excludes grammY, D1 and Telegram subrequests.
- **Needs Divine (architecture decision, nothing adopted):** choose how to proceed. Options: (a) the parked "nightly pre-computed grids" idea (the nightly job stores each match's grid; the Worker only looks them up; needs a PRD bump and a new architecture version); (b) F2, split the work across several invocations; (c) F3, offload to GitHub Actions; (d) accept the risk on the Free plan, given Cloudflare's tolerance for occasional overruns, with an explicit ADR (not recommended: cold requests are the normal case); (e) the Workers Paid plan, which lifts the CPU limit (cost decision). Stage 2 (ingestion, fit) does not depend on the Worker grid code, but it has its own legal gate (register unsigned, A-1 undecided, `data/historical_teams.json` missing).
- **Still pending:** switch `SPIKE_ENABLED` back to `"0"`; fold the deferred `docs/setup.md` C8 rewrite into a docs PR; live D1 probe.

### Module status
| Module | Status |
|---|---|
| Stage 1: Foundations and CPU spike | **in-progress** (deployed; CPU gate failed after F1, awaiting Divine's decision) |
| Stages 2 to 7 | not started |

---

## 2026-10-16 (late night) — Stage 1 closed; Divine chose pre-computed grids (Stage 1 complete)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1).
- **Decision (Divine, this session):** the CPU gate failed after F1 (p95 16 ms, max 22 ms; PR #8), and Divine chose the parked **nightly pre-computed grids** option. F2, F3 and the paid plan are not adopted. This changes the architecture (the nightly job stores per-match grids; the Worker looks them up and the TypeScript grid port in the Worker goes away), so it needs a **PRD bump and a new architecture version made in design chat (System Designer)**. Nothing in the Worker has been changed for it. Until those files exist, `essential_1` stays the scope and the version-alignment check stays N=1.
- **Done:** PR #8 merged (CPU gate result after F1). This session's PR switches `SPIKE_ENABLED` back to `"0"` in `apps/bot/wrangler.toml` and rewrites `docs/setup.md` C8 to the current method. The spike code stays in place, deprecated, not deleted (extensibility rule).
- **Stage 1 exit criteria (essentials step 9):** CI green on `main`; Worker deployed; webhook rejects bad requests and acks good ones; migration `0001` applied to the real D1; CPU measurement recorded (`docs/verification.md` section 2); this entry written. All met.
- **Carried over, not blocking Stage 2:** live D1 probe (verify item 3; needs the nightly token in Divine's shell); architecture inventory gap (`TELEGRAM_WEBHOOK_SECRET` and `WORKER_URL` as GitHub secrets, for the next snapshot); the `claude.md` in-place-edit exception; missing `SYETEM DESIGN RULES.html`; git identity.
- **For the design chat:** the pre-computed grids change should cover where grids are stored (D1 table and size against the free storage and row limits), how many days of fixtures, what the Worker does when a grid is missing (fallback), how grids relate to the first-prediction-immutable rule, and the golden-vector rule for numerics (Python becomes the only grid implementation).

### Module status
| Module | Status |
|---|---|
| Stage 1: Foundations and CPU spike | **complete** |
| Stage 2: Ingestion, aliases and bootstrap | not started (legal gate: register unsigned, A-1 undecided, `data/historical_teams.json` missing) |
| Stages 3 to 7 | not started (Stages 5 and 7 are affected by the pre-computed grids decision) |

---

## 2026-10-17 — Stage 2 prerequisites done (Stage 1 complete; Stage 2 not started)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1).
- **Legal register signed (Divine Gima, 2026-10-16):** football-data.org **enable**; A-1 **path 2** (football-data.org only, Scottish Premiership dropped, football-data.co.uk not used at all). Flags are still off in code. The `FD_ORG_TOKEN` GitHub secret was added by Divine.
- **Consequences of path 2 (architecture ADR-035):** no 3-season history from co.uk and no shots; SPL gets `INSUFFICIENT_HISTORY` and the screener prompt stops listing it. If the free tier returns only the current season, most teams stay under 10 matches for weeks (warm-up). The free-history depth is the open measurement: one authenticated request for a past season, after Stage 2 starts.
- **Data files added:** `data/canonical_teams.json` (generated from PRD_1 section 12; 179 clubs, counts match the PRD table) and `data/historical_teams.json` (**DRAFT**, 59 history-only clubs from memory, cross-checked against the 2026-27 lists; 9 marked `verify`; SPL clubs left out; Divine to review). Per-source aliases come in Stage 2 under `data/aliases/`.
- **Module status:** Stage 1 complete. Stage 2 not started.

---

## 2026-10-17 — Stage 2 built (ingestion, aliases, bootstrap); live runs pending (in-progress)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1), under A-1 **path 2** (football-data.org only; co.uk not used; SPL dropped).
- **Done (code, tests green: 187 pytest, ruff, mypy strict, repo rule checks):**
  - Migration `0002` (competitions, teams, team_aliases, matches, source_fetch_log); additive, forward-only.
  - `footy.aliases` (normaliser with FC/AFC rule, resolver, validated seed loader), `data/aliases/fd_org.json` (best-effort spellings; the dry-run's unmapped report corrects it).
  - `footy.ingest` (paced football-data.org client with bounded retries, strict payload parser, `bootstrap` and `ingest` pipelines), `footy.reconcile` (ADR-010 90-minute rule, forward-only status, disagreement limit of 3, natural-key clash handling), repository modules in `footy/repo` (the only SQL), `footy` CLI with exit codes 0/1/2/3.
  - `.github/workflows/data.yml` (manual: `bootstrap-dry-run`, `bootstrap`, `ingest`, `d1-probe`), main-only, secrets from GitHub.
  - football-data.org v4 facts checked in the official docs (`docs/verification.md` section 4). Notable: `fullTime` includes extra time and the shootout; `regularTime` is the 90-minute score.
- **Not built (by decision/stage):** co.uk CSV loader and the two-source +/-1-day join (path 2 drops co.uk); Telegram alert sending (Stage 7; Stage 2 writes the deduped `events` rows it will send); score/fit/publish commands (later stages).
- **Open before Stage 2 can be called complete (needs live runs, user starts them from the Actions tab):** (1) `bootstrap-dry-run` to measure free-history depth and list unmapped club names; (2) alias fixes from that report; (3) `bootstrap`; (4) `ingest`; (5) exit criteria check: matches populated and consistent, zero unmapped or a documented list; (6) optional `d1-probe`.
- **Risks to watch:** free tier may return only the current season, which means teams stay below 10 matches for weeks (warm-up) and the UCL-only clubs likely stay INSUFFICIENT_HISTORY; the `fd_org.json` spellings are unverified until the dry-run.
- **Module status:** Stage 2: code `complete`, live verification `in-progress`. Stages 3 to 7 not started.

---

## 2026-10-17 (later) — Stage 2 live runs, code review of Stages 1 and 2, source-of-truth alignment; Stage 2 CLOSED

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1; Rev-3 notes added today, version unchanged).
- **Stage 2 live results (GitHub Actions workflow `data`, production D1):**
  - `bootstrap-dry-run`: 9,280 matches fetched (9 competitions x 3 seasons), every record parsed, no anomaly or outage. **The free plan returns all three seasons** (2024-25, 2025-26, 2026-27), so there is no warm-up problem. 509 matches were skipped only because 15 club spellings were unknown; added to `data/aliases/fd_org.json` with a regression test each (PR #12).
  - `bootstrap`: 10 competitions, 179 active + 59 history-only teams, 616 aliases, **9,280 matches inserted**, 0 unmapped, 0 anomalies, 27 fetches logged. Direct D1 checks: 0 impossible goal values, 0 self-matches, 0 orphan teams; 6,802 finished results all verified (6,794 `ft_90`, 8 `regular` after extra time); 3 `AWARDED` kept as `unverified` with no goals; fixtures to May 2027 present.
  - `ingest`: window 2026-10-09..2026-10-19 accepted by the API (no range-limit problem); 11 matches updated, 152 unchanged, 0 changed results; team-list check resolved all clubs in all nine competitions (including 36 in the Champions League). 15 `status_regression` events: the source reported finished matches as `TIMED` again; the forward-only rule kept the stored results (working as designed).
  - 29 clubs have fewer than 10 verified matches: the 11 Scottish clubs (league dropped), 5 Champions League-only clubs (2 each) and recently promoted clubs (5 to 8). This is the `INSUFFICIENT_HISTORY` rule operating, not a defect.
- **Code review (`/code-review` high, apps/ scripts/ db/ .github/ data/): 12 findings. Fixed (real):**
  1. Worker: every message from a non-allowlisted sender wrote an `events` row (quota exhaustion risk). `events.record` now supports a real 24 h dedupe key; ignored updates use an hourly key (at most 24 rows a day). Tests added.
  2. Fit job: `D1Error` was not caught, leaving `job_runs` at `running` and losing the fetch log. Both jobs now catch it, record the failure best-effort and return exit 1. Tests added (database failure; database fully down).
  3. `RequestsTransport` read the body with `raw.read`, whose urllib3 errors skipped the retry loop. Now uses `iter_content` with a size cap and closes the response; mid-body failures are retried. Tests added with a stub session.
  4. Anomaly events were written without a dedupe key and would repeat every night. Now one per anomaly per 24 h.
  5. `run_ingest` took an unused `ref` and the CLI loaded the local data files for `ingest`, adding a failure mode. Removed. A stale progress file now gives a clear `DataError` instead of a `KeyError`.
  6. `scripts/smoke.mjs` failed on any old Telegram `last_error_message`. Only an error from the last 15 minutes counts now. Test added.
- **Reviewed and not changed (with reason):** ingest window possibly too long for the API (disproved by the live run); matches not resuming (disproved: the write plan compares with stored rows, so a rerun sends only the missing rows; a test now proves it); `start_job` and keyless events not idempotent on a lost response (worst case one extra row; accepted); spike route buffering the body (route is off and deprecated); hard-coded `CHECK` lists (they are the architecture's schema; a new competition would be a rebuild migration, noted); `walk.mjs` skip list (those folders are git-ignored, so nothing in them can be committed).
- **Source-of-truth alignment (Rev-3, at Divine's explicit instruction; version stays 1):** `system_architecture_1.md` header, §4.3 (A-1 outcome), §7.6, §8.5, §8.10, §9.1 (inventory gaps closed), §9.3 (`data.yml`), §9.8, §14 (ADR-013 status, new ADR-037 pre-computed grids direction, ADR-038 manual data workflow), §16 (ledger outcomes for items 1, 2, 3, 7), §18 (Rev-3 table). `essential_1.md` header, Stage 1 step 8 and Stage 2 step 1 outcomes. `docs/verification.md` rows 3 and 7. **`PRD_1.md` is untouched:** it still lists the Scottish Premiership and the Worker computing grids; both changes (path 2 and ADR-037) must be carried into PRD_2 by design chat.
- **Verification today:** pytest 210, Vitest 76, script tests 47, ruff, mypy strict, Biome, repo rule checks, migration lint all green.
- **Needs Divine / design chat:** PRD_2 + architecture_2 + essentials_2 for the pre-computed-grids design (changes Stages 5 and 7); decide how the PRD should treat the dropped Scottish Premiership; review the 9 `verify` clubs in `data/historical_teams.json` (none caused an unmapped name in the live runs, so the draft covered every club that appeared); the `claude.md` rule against in-place edits has no recorded exception for Rev-1 to Rev-3 (unchanged open issue).
- **Still open (not blocking):** live `d1-probe` (atomicity of batches), `SYETEM DESIGN RULES.html` missing, git identity, Time Travel retention.

### Module status
| Module | Status |
|---|---|
| Stage 1: Foundations and CPU spike | **complete** (CPU gate failed; pre-computed grids chosen; redesign pending in design chat) |
| Stage 2: Ingestion, aliases and bootstrap | **complete** (code, live bootstrap and ingest verified, review findings fixed) |
| Stage 3: Dixon-Coles, backtest harness, metrics | not started; next |
| Stages 4 to 7 | not started (Stages 5 and 7 wait for the new architecture version) |

---

## 2026-10-17 (night) — Stage 3 built: Dixon-Coles, scoring, backtest, golden vectors (code complete; live backtest pending)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md`, Stage 3 (all N=1; alignment and drift checks clean). Branch `feat/stage-3-dixon-coles`.
- **Done (tests green: 287 pytest, ruff, mypy strict, repo rule checks):**
  1. `footy.models.grid`: 13x13 grids (independent Poisson, Dixon-Coles tau, bivariate Poisson already for Stage 4), markets, linear pool, extreme-fixture guard.
  2. `footy.scoring`: RPS (1X2 and totals), log loss, Brier per over line, league-frequency baseline, calibration bins; hand-computed tests.
  3. `footy.models.structure` and `dixon_coles`: pooled attack/defence with league offsets and ridge shrinkage, time-decay weights, 1,095-day window, vectorised negative log-likelihood with analytic gradient (checked against finite differences), L-BFGS-B, sanity checks, `failed` outcome instead of a silent fallback.
  4. `footy backtest` (`footy.backtest`): walk-forward folds fitted only on earlier matches (a spy test proves no leakage), baseline from the same training window, per-competition and overall RPS, paired difference, optional half-life and shrinkage sweep, text report, `job_runs` record. `data.yml` gained a `backtest` command.
  5. Golden vectors `packages/contracts/golden/dc_grid_v1.json` plus a write/check module and test.
  6. Synthetic league generator and parameter-recovery test (correlation above 0.93, home advantage and rho within 0.06 of the truth).
  7. New dependencies: `numpy`, `scipy` (runtime), `hypothesis` (dev); lockfiles regenerated with hashes. No `penaltyblog`, no pandas.
- **Hand mutations (6, each caught):** tau sign, RPS normalisation, training on the fold's own matches, decay sign, a tau gradient sign, the home-advantage gradient.
- **Findings:** (a) the 1e-6 tail claim in architecture section 8.1 holds per side only up to about 2.3 goals (measured; recorded in `docs/verification.md` section 5; for the next architecture snapshot). (b) a test exposed a real crash path (negative tau for an extreme fixture); fixed with the guard. (c) `cli.py` now applies the football-data.org legal gate only to `bootstrap` and `ingest`, so model commands need only the D1 token.
- **Open (Stage 3 exit criterion):** run the `backtest` command from Actions after merge, record the numbers in `docs/verification.md` section 5, and state whether Dixon-Coles beats the baseline (essentials Stage 3 step 8). If it does not, the shortfall must be documented and escalated to Divine.
- **`fit` command:** the essentials list it under Stage 3, but a fit run is persisted in tables that Stage 4 creates (ADR-033), so `footy fit` and `footy publish` land in Stage 4.

### Module status
| Module | Status |
|---|---|
| Stage 1, Stage 2 | **complete** |
| Stage 3: Dixon-Coles, backtest harness, metrics | code **complete**; live backtest and the baseline verdict **in-progress** |
| Stage 4 | started on a stacked branch at Divine's request (see next entry when written) |
| Stages 5 to 7 | not started (Stages 5 and 7 wait for the new architecture version) |

---

## 2026-10-17 (night) — Stage 4 built: pi-rating, bivariate Poisson, ensemble, team form, fit and publish (code complete; live runs pending)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md`, Stage 4 (all N=1). Branch `feat/stage-4-ensemble-publish`, **stacked on `feat/stage-3-dixon-coles` (PR #14)**.
- **Process note (for Divine):** Stage 4 was started before Stage 3's live exit criterion (the real backtest) was met, because Divine asked for both stages in one session. The essentials say a stage's exit criteria come first. Nothing in Stage 4 depends on the backtest numbers except the optional initial ensemble weights, and the `fit` job reads them if they exist. Merge PR #14 first, run `backtest`, then merge this one.
- **Done (tests green: 389 pytest, 81 Vitest; ruff, mypy strict, repo rule checks, migration lint):**
  1. `pi_rating.py`: constants verified against the paper (verify-at-build item 8, `docs/verification.md` section 6; the recalled 0.06 / 0.5 were wrong, the paper's optimum is lambda 0.035, gamma 0.7); hand-computed update tests; rating-to-grid mapping with a fitted difference scale (hypothesis).
  2. `bivariate_poisson.py`: Karlis-Ntzoufras, analytic gradient from the pmf-difference identity (checked against finite differences), recovery test on data generated from a bivariate Poisson.
  3. `ensemble/`: softmax of negative recent RPS, shrunk toward the backtest prior (equal weights without one); hand-computed tests.
  4. `form/`: `team_form` for every active team (including those with no matches, so the 95% coverage check is meaningful).
  5. Migration `0003` (`model_runs`, `active_run`, `model_params`, `team_form`); `repo/models.py`; the Stage 2 migration test and the Worker table-list test were updated for the new tables.
  6. `footy fit` (writes a `building` run; a failed model is stored `failed` with its reason, exit 4; all failed gives a `failed` run), `footy publish` (promotion gate: structural checks, hash re-verification, stability guard; one atomic guarded batch; supersede; prune to 30; `--rollback`); `alerts` stub writes deduped `alert` events.
  7. Backtest now compares dc / pi / bp, the ensemble (weights from earlier folds only) and the baseline, per competition; `data.yml` gained `fit` and `publish`.
  8. Golden vectors for all three grid builders (`packages/contracts/golden/{dc,pi,bp}_grid_v1.json`).
  9. Worker: `RunRepository.readActive()` reads the active run through the pointer in one batch, with `payloadVerifies` (SHA-256); Vitest proves a promoted run is readable and follows a rollback (Stage 4 exit criterion).
- **Tests required by the essentials:** corrupted-run and jumped-parameters fixtures are rejected and the old run stays active; hand-computed ensemble weights and shrinkage; pi-rating hand examples; atomic promotion with an injected failure; rollback; pruning keeps the active run.
- **Hand mutations (17 over both stages, each caught):** the last one that first survived (building `team_form` only for teams with matches) led to a new integration test with matchless active teams.
- **Findings:** (a) the first draft of `start_job` handling let a database outage at job start escape as an exception; the three new jobs now return a result. (b) pi-rating constants recalled from memory were wrong; checked against sources. (c) the PDF's equation glyphs did not extract; the exact formula rests on the paper's prose, the author's 2022 restatement and the R package defaults, which agree (recorded as a caveat).
- **Open (Stage 4 exit criteria that need live data):** run `backtest` with `models=dc,pi,bp` on production, `fit`, then `publish` once, and record the numbers and the verdict (does the ensemble beat the baseline and each model; is any model worse than the baseline) in `docs/verification.md` section 6. A model that does not beat the baseline must be documented and escalated, not hidden.
- **For the design chat (ADR-037, pre-computed grids):** the grid builders and golden vectors exist in Python only as the reference; if Python becomes the only implementation, `fit` is the place where per-match grids would be produced, but that needs PRD_2 and a new architecture version.

### Module status
| Module | Status |
|---|---|
| Stage 1, Stage 2 | **complete** |
| Stage 3: Dixon-Coles, backtest harness, metrics | code **complete** (PR #14); live backtest verdict **in-progress** |
| Stage 4: Pi-rating, bivariate Poisson, ensemble, publishing | code **complete** (stacked PR); live backtest, first `fit` and `publish` **in-progress** |
| Stages 5 to 7 | not started (Stages 5 and 7 wait for the new architecture version) |

---

## 2026-10-17 (night, later) — Stages 3 and 4 CLOSED: live backtest, first fit and first publish

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1). PRs #14 (Stage 3), #15 (Stage 4), #16 (fold failure reasons) and #17 (optimiser cap) merged; the deploy applied migration `0003` to the real D1.
- **What the live runs showed** (full tables in `docs/verification.md` sections 5 and 6):
  - Stage 3 exit criterion met: Dixon-Coles RPS 0.2044 against the baseline's 0.2309 over 2,533 matches, ahead in all nine competitions. The half-life / shrinkage sweep is flat (0.2041 to 0.2061); starting values kept.
  - Stage 4: every model and the ensemble beat the baseline overall and in all nine competitions (RPS: baseline 0.2304, pi 0.2076, dc 0.2042, bp 0.2042, ensemble 0.2040). dc, bp and the ensemble are statistically indistinguishable; pi is the weakest. Totals RPS barely improves on the baseline.
  - First `fit` (3 models ok, 225 team_form rows) and first `publish` (gate passed): run `R20261016T232312Z` is active.
- **Problems found by the live runs and fixed:** (1) the first backtest exited with code 4 because 3 of 23 folds hit the 500-iteration cap; the job gave only a count, so PR #16 added the fold, size and error to the report; (2) the second showed bivariate Poisson hitting the cap in 2 folds; PR #17 raised the cap to 3000 and relaxed the tolerance to 1e-10 (same optimum, fewer iterations). The clean rerun had no failed folds. Lesson: synthetic tests did not reproduce real-data convergence, so a real-data run was necessary before the first fit.
- **Exit criteria:** Stage 3 (DC beats baseline or shortfall documented): met. Stage 4 (a promoted run readable through the Worker repo path; gate rejection tested; tests green): met; the Worker read path is proven in Vitest against local D1, and a real run is now in production D1.
- **Carried forward / not blocking:**
  1. The stability guard and `--rollback` have not yet run against the live service (needs a second run); they are covered by SQLite tests, including an injected mid-promotion failure. D1 batch atomicity on the live service is still unconfirmed (verification item 3).
  2. Bivariate Poisson is the slowest fit (about 20 s on a production-sized world); the nightly budget of 15 minutes is not threatened.
  3. For the next architecture snapshot (design chat): the section 8.1 tail claim holds only up to about 2.3 goals per side; the ensemble kappa (100) and the stability bound (0.5) are starting values; the `fit` command listed under Stage 3 actually landed in Stage 4 (ADR-033); ADR-037 would make `fit` the producer of per-match grids.
  4. Still open from before: PRD_2 / architecture_2 / essentials_2 for pre-computed grids (Stages 5 and 7 wait for it), the `claude.md` in-place-edit exception, the missing `SYETEM DESIGN RULES.html`, git identity, live `d1-probe`.

### Module status
| Module | Status |
|---|---|
| Stage 1: Foundations and CPU spike | **complete** |
| Stage 2: Ingestion, aliases and bootstrap | **complete** |
| Stage 3: Dixon-Coles, backtest harness, metrics | **complete** |
| Stage 4: Pi-rating, bivariate Poisson, ensemble, publishing | **complete** |
| Stages 5 to 7 | not started (Stages 5 and 7 wait for the new architecture version) |

---

## 2026-10-17 (end of session) — Code review of Stages 3 and 4; source of truth aligned (Rev-4)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1; Rev-4 notes added today, version unchanged). Branch `docs/review-and-source-alignment`.
- **Session summary (what was done today, in order):** Stage 3 and Stage 4 implemented and merged (PRs #14, #15); live `backtest`, `fit` and `publish` run from Actions; two real-data problems found and fixed (#16 fold failure reasons, #17 optimiser cap and tolerance); results and closure recorded (#18); this review and alignment (this PR).
- **Code review (`/code-review` high, over PRs #14 to #17): 9 findings, none fixed in this session** (Divine asked for a review, not for changes). Each is Problem, Why, Fix. Recommended order is by risk.

| # | Where | Problem | Why it matters | Fix |
|---|---|---|---|---|
| 1 | `.github/workflows/data.yml` | `FD_ORG_TOKEN` and `SOURCE_ENABLED_FDORG=1` are in the environment of every command, including `fit`, `publish`, `backtest` | Least privilege: model commands run numpy/scipy and need only D1; a dependency bug could read the football-data.org token, and the legal flag is on where it should not matter | Set the `FD_ORG_*` variables only for `bootstrap`, `bootstrap-dry-run` and `ingest` (a conditional expression on `inputs.command`, or separate jobs) |
| 2 | `backtest/job.py`, `fitting.py` | The stored backtest `result` is the FIRST sweep combination; `fit` takes the newest ok or partial `backtest` job of any shape (any model set, any `--test-days`) as the ensemble prior | The prior can come from a configuration the fit never uses (for example half-life 200, shrinkage 2, dc only). The live run happened to use the clean 300 / 4 three-model run | Store the config and model list with the summary and use a prior only when the models match (and the fit config matches, or say so); prefer the default-config result in sweeps |
| 3 | `models/bivariate_poisson.py`, `models/golden.py` | `BpModel.grid` passes lambda3 through `clip_rate`, which floors at 0.01, but the fit allows lambda3 down to about 0.0003 | A small fitted covariance is served 5 times too large, so the served grid no longer matches the fitted likelihood; the golden vector labelled "almost no covariance" (0.0005) is actually clipped to 0.01 and so cannot catch it | Floor lambda3 at `exp(LOG_LAMBDA3_BOUNDS[0])` and clip only the top; regenerate `bp_grid_v1.json` and the test that reads it. Real fitted lambda3 values are probably well above 0.01 (a test world gave about 0.12), so the live impact is likely small |
| 4 | `publish/gate.py`, `publish/job.py` | `n_teams_training` falls back to 0 when a run's diagnostics lack it, which switches the payload-coverage check off; the active run's payloads used for the stability guard are not hash-verified | A malformed or hand-edited run could skip a check; a corrupt active payload would produce a wrong comparison | Fail the gate when `n_teams_training` is absent; verify the active run's payload hashes before comparing (and skip the guard with a reason if they fail) |
| 5 | `backtest/walkforward.py` | The per-model RPS histories used for ensemble weights are appended only when that model forecast the match, then treated as aligned | If a model skips matches or fails a fold, the last-n windows cover different fixtures, so the weights compare unequal samples (in the live run bp failed in two folds before the fix) | Append only when every fitted model forecast the match, or key the history by match |
| 6 | `fitting.py` | `data_cutoff_utc` is the newest stored result even when `--as-of` excludes later matches | The column is documented as the latest result included; the Worker's staleness logic and any audit would be wrong for an `--as-of` run (the normal nightly run is unaffected) | Use `max(match_date)` of the window (what `training_to` already holds) |
| 7 | `repo/ops.py` and the three jobs; `models/bivariate_poisson.py` | A job killed by the 45-minute timeout leaves its `job_runs` row at `running` forever. Bivariate Poisson is the slowest part (about 20 s per fit; four pmf passes per objective evaluation) | Silent stale rows; a large sweep with all three models could approach the timeout | Mark `running` jobs older than the timeout as `failed` at the start of the next run; cache the gammaln tables per `Structure`; do not refit pi for different shrinkage values |
| 8 | `repo/models.py`, `db/migrations/0003` | The CHECK lists on `model` and `status` mean a fourth model needs a table rebuild, while code comments called adding a model "additive" | Misleading comment; a rebuild in one change is what the migration rules warn about | Keep the CHECK (the architecture fixes it) and correct the comment. Done in the architecture section 5.4 (Rev-4); the code comment in `models/registry.py` still needs the same wording |
| 9 | `apps/bot/src/repo/index.ts` | `readActive` reads every model's whole payload (about 10 to 60 KB each) and the helper hashes it in the Worker | If called per webhook update in Stage 5 it costs D1 reads and Worker CPU against the 6 ms gate | Read only the small pointer each time; fetch, verify and parse the payloads when `run_id` changes and keep them in module scope. Moot if the pre-computed-grids design (ADR-037) removes payload reads from the Worker |

  Also noted by the review as a maintainability point (not a bug): `DcModel` and `BpModel`, `_utc_now` (four copies), the job start/finish boilerplate, and the SHA-256 payload hash (in `fitting.py` and again in `publish/gate.py`) are duplicated. Fix by a shared base class and `run_lbfgs` helper, one clock helper, and importing `payload_sha256` in the gate. The earlier optimiser fix had to be applied twice (PRs #16 and #17), which is the cost of the duplication.
- **Other open design point from the review (not a defect):** the stability guard has no override. After a legitimate large move every later run is compared with the same active run and rejected until someone intervenes. Add an explicit, logged `--accept-drift RUN_ID` path before nightly runs are automated (Stage 7).
- **Source-of-truth alignment (Rev-4, at Divine's explicit instruction; version stays 1):** compared practice with the three source files.
  - `system_architecture_1.md`: **corrected.** Header Rev-4 line; section 5.4 (every active team has a `team_form` row; CHECK lists need a rebuild to extend); section 6.7 (real CLI options, exit code 4 cases, legal gate only for data commands); section 7.6 (modules as built); section 8.1 (the 1e-6 tail claim measured to hold per side up to about 2.3 goals; extreme-fixture guard, ADR-039); section 8.2 (as-built notes: shared pooled structure, no warm start, optimiser settings, pi constants and fitted scale, window ends at the cut-off); section 8.3 (backtest-derived prior, kappa 100, ADR-040); section 8.6 (as-built gate numbers, promotion batch, pruning, rollback; ADR-041); section 9.3 (`data.yml` commands); section 14 (ADR-039 to 041); section 16 (item 8 verified, results); section 18 (Rev-4 table).
  - `system_architecture_essential_1.md`: **corrected.** Rev-4 tags on Stage 3 steps 4, 6, 7 and 8 (outcome: met), Stage 4 steps 1, 3, 4, 5, 6, 8 and 9 (outcome: met), and the Stage 3 component list note that `fit` landed in Stage 4.
  - `PRD_1.md`: **not touched.** Nothing built in Stages 3 and 4 contradicts it (models, ensemble weighting from rolling RPS, walk-forward backtest and the success metric are as written). The two known PRD gaps (the Scottish Premiership and the Worker computing grids) are unchanged and belong to PRD_2 from the design chat.
  - `claude.md` still forbids in-place edits and still has no recorded exception for Rev-1 to Rev-4; each was done at Divine's explicit instruction.
- **Not done (needs Divine):** decide which review findings to fix and when (suggested: 1, 2, 3 and 4 in one small PR; 5 and 6 in another; 7 and the duplication refactor before Stage 7; 9 with the Stage 5 redesign); the pre-computed-grids redesign in the design chat (PRD_2, architecture_2, essentials_2); the `claude.md` exception; the missing `SYETEM DESIGN RULES.html`; git identity.

### Module status
| Module | Status |
|---|---|
| Stages 1 to 4 | **complete** (review findings above are follow-ups, none blocks Stage 5) |
| Stages 5 to 7 | not started (Stages 5 and 7 wait for the new architecture version) |

