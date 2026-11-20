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

---

## 2026-10-17 (end of session, later) — All review findings repaired; source of truth re-aligned (Rev-4)

- **Built against:** `PRD_1.md`, `system_architecture_1.md`, `system_architecture_essential_1.md` (all N=1). Branch `fix/code-review-stage-3-4`.
- **Done: every finding of the previous entry's table, plus the duplication and the override** (Divine asked for all of them to be repaired). Tests: 410 pytest (was 389), 85 Vitest (was 81), 47 script tests; ruff, mypy strict, Biome on changed files, repo rule checks, golden check all clean. 12 hand mutations of the fixes, each caught.

| # | Finding | What was done |
|---|---|---|
| 1 | FD token and legal flag in every `data.yml` command | Set only for `bootstrap-dry-run`, `bootstrap`, `ingest`; the dry run gets no D1 token; a test reads the workflow file and fails if `fit`, `publish`, `backtest` or `d1-probe` could receive them |
| 2 | Ensemble prior from any backtest | `prior_from_backtest` now needs the same half-life and shrinkage as the run and at least 200 forecasts per model; the backtest reports the production-settings cell of a sweep; the summary names its models and `test_days` |
| 3 | Covariance floored at 0.01 when served | New `clip_covariance` (floor 1e-4, below the fit bound); `bp_grid_v1.json` regenerated; the "almost no covariance" vector is now genuinely unclipped, with tests |
| 4 | Gate skippable by omission; unverified active payloads | A run without `n_teams_training` is rejected; the stability guard compares only with verified active payloads and records a skip reason otherwise |
| 5 | Misaligned RPS histories | A match enters the ensemble history only when every fitted model forecast it (`rps_history` exposed and tested with a model that skips teams) |
| 6 | `data_cutoff_utc` ignored `--as-of` | It is the latest result actually used; the newest stored result is reported separately |
| 7 | Stale `running` jobs; fit speed; pi refits | `fail_stale_jobs` (60 minutes) at the start of fit, publish and backtest; log-factorial table makes bivariate Poisson about twice as fast (same objective and iterations); the pi fit is cached across sweep shrinkage values |
| 8 | "Adding a model is additive" comment | Corrected in `models/registry.py` (architecture 5.4 was corrected earlier) |
| 9 | Worker read whole payloads per call | `runs.readPointer()` (one small row) and `runs.readActiveVerified()` (fetch, hash and keep payloads only when the pointer changes; `clearActiveRunCache()` for tests); 4 new Vitest cases |
| dup | Duplicated model code, clock, job boilerplate, payload hash, `Fitter` name | `models/pooled.py` (shared team table, payload, optimiser), `clock.py`, `jobs.py` (`JobResult`, `run_job`), `payload.py` (one hash used by fit and gate); `types.Fitter` renamed `FitFunction` |
| override | Stability guard had no override | `footy publish --run-id ID --accept-drift`: skips only the stability guard for that run, needs an explicit run id, logs a `drift_accepted` event; structural checks still apply |

- **Source-of-truth alignment (Rev-4, at Divine's explicit instruction):** compared the fixes with the documents. `system_architecture_1.md` corrected (sections 6.7, 7.6, 8.1, 8.2, 8.3, 8.6, 9.3, 9.4, ADR-039, Rev-4 table); `system_architecture_essential_1.md` corrected (Stage 4 steps 4 and 6); `docs/verification.md` notes the speed-up and that the recorded backtest numbers predate the fixes. **`PRD_1.md` untouched:** nothing here changes a requirement or contradicts it.
- **For Divine:** merge the PR, then re-run `backtest` with `models=dc,pi,bp` (single half-life 300, shrinkage 4) to refresh the numbers; two rows can move slightly (the ensemble and a very small bivariate covariance) and no conclusion is expected to change. The next `fit` and `publish` pair will also exercise the stability guard for the first time against a real previous run.
- **Still open (unchanged):** the pre-computed-grids redesign in the design chat (PRD_2, architecture_2, essentials_2; Stages 5 and 7 wait for it), the `claude.md` in-place-edit exception, the missing `SYETEM DESIGN RULES.html`, git identity, live `d1-probe`.

### Module status
| Module | Status |
|---|---|
| Stages 1 to 4 | **complete**; review findings repaired |
| Stages 5 to 7 | not started (Stages 5 and 7 wait for the new architecture version) |

---

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
