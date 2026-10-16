# Verification record (Essentials 1, Stage 1)

What was verified, how, and what is still open. Numbers marked **indicative** are not the ADR-013 gate.

## 1. Verify-at-build items (architecture section 16)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | football-data.org free-history depth, fields, terms | **Open.** The register is now signed (2026-10-16). Fields and parameters are confirmed from the v4 docs (section 4). The free-history depth is settled by `footy bootstrap --dry-run` (workflow `data`, command `bootstrap-dry-run`); result goes in section 4 | `docs/legal/source_terms_register.md` section 1, section 4 below |
| 2 | football-data.co.uk terms for hand download; CSV headers | **Checked, not conclusive.** The site is "for private individuals" and "league match prediction only"; manual download is not addressed. CSV column headers are verified in Stage 2 against hand-written fixtures | Register section 2 |
| 3 | D1 REST batch support and the 100-bound-parameter limit | **Partly verified.** The OpenAPI spec accepts `{"batch": [...]}` and a single `{sql, params}`. The 100-parameter limit and batch atomicity are **not confirmed from documentation**; the live probe `python -m footy.repo.d1_probe` answers both once a real D1 exists. The client enforces 100 and is tested against a fake. | Cloudflare API spec, `d1_probe.py`, `tests/test_d1_probe.py` |
| 4 | Workers Logs retention; D1 Time Travel retention (Free) | **Workers Logs: 3 days on Free** (7 days from the 2026-12-01 observability pricing change). Pull `cpuTime` within 3 days of the spike. **Time Travel retention: not confirmed** in this session; check in the dashboard before the Stage 7 restore drill | Cloudflare docs, Workers pricing page |
| 5 | GitHub branch protection and environments on a private Free repo; 60-day auto-disable | **Branch protection and deployment protection: not available** for private repos on Free (search of GitHub docs, secondary sources agree). **Compensating controls are wired:** committed `pre-push` hook (tested against a real `git push`), `deploy.yml` merged-PR guard, `CF_DEPLOY_TOKEN` referenced only from `deploy.yml`. 60-day auto-disable: documented for public repos only; confirm once at the Stage 7 schedule check | `scripts/hooks/pre-push`, `scripts/verify-merged-pr.mjs`, `.github/workflows/deploy.yml` |
| 6 | soccernews.com terms | **Checked.** Personal, non-commercial use only; the system never reads the site | Register section 3 |
| 7 | Worker CPU of the real engine (ADR-013 spike) | **Pending production measurement.** Indicative local numbers in section 2 | Section 2 |
| 8 | Pi-rating constants | Stage 4 | none |

Other facts found while building (re-verify, limits change):
- D1 Free daily row read and write limits have been **hard-enforced since 2026-09-01**: queries fail until 00:00 UTC. The client raises `D1QuotaError` and does not retry.
- Workers Free CPU limit and request limits: as in architecture section 16 (not re-checked this session).
- The Workers test package was renamed: use `@cloudflare/vitest-plugin` (v1), not `@cloudflare/vitest-pool-workers`.
- The Worker bundle is about 789 KiB (126 KiB gzip), mostly Zod. This is far below the Free plan's size limit; Zod's startup cost should be re-read from the deployed Worker.

## 2. CPU spike (ADR-013, Essentials 1 Stage 1 steps 7 and 8)

**What the spike runs** (`apps/bot/src/spike`, path `POST /spike/<WEBHOOK_PATH_SECRET>`, off unless `SPIKE_ENABLED=1`): parse a 60-match, ~47 KB schema-v1-shaped upload, validate it with a Zod placeholder schema, parse three ~45-51 KB model blobs (module-level strings standing in for D1 rows), then per match build three 169-cell grids (Dixon-Coles tau, independent Poisson from a pi-style goal difference, bivariate Poisson convolution), linear-pool them, derive 1X2 and six over lines from the pooled grid, render and split replies at 3,900 characters.

**What it leaves out (so a pass here is optimistic by roughly this much):** grammY glue (estimated 0.5-2 ms in section 8.10), the D1 reads and writes, and Telegram `getFile`/`sendMessage` subrequest handling. Stages 5 and 7 re-measure the real path.

**Method (production, the gate):** deploy with `SPIKE_ENABLED=1`, run `node scripts/cpu-spike.mjs --n 25`, then export the invocation records (Workers Logs, or `wrangler tail --format json`) and run `node scripts/cpu-stats.mjs <file> --min 20`. It prints p50 / p95 / max and the verdict. `cpuTime` is whole milliseconds, so a reported "6" can hide 5.5-6.4 ms. Switch the path off after recording.

**Indicative local result (Node 24 on Divine's Windows laptop, NOT workerd, NOT the gate):** the bundled Worker answered the 60-match upload in a p50 of about **9-14 ms** and a p95 of about **14-30 ms** of wall time over 60 invocations, across 3 runs, with high run-to-run noise. Breakdown (p50, per request): JSON parse of the upload 0.4 ms, Zod 0.8 ms, parse of three blobs 2.2 ms, 60 Dixon-Coles grids 0.4 ms, 60 independent grids 0.8 ms, 60 bivariate-Poisson grids 1.3 ms, pool and markets 0.6 ms, the rest (rendering, allocation, lookups) the remainder.

**What this suggests, honestly:** the workload as designed is at risk of exceeding the 6 ms p95 target. The largest single costs are parsing the model blobs and validation, which is exactly what F1 targets (fetch per-team rows instead of whole blobs, drop Zod for bulk arrays). Server CPUs are usually faster than this laptop, so the production number may well be lower, but this must not be assumed. **Decision gate (step 8) is open until the production measurement exists.** If p95 > 6 ms: apply F1 and re-measure; F2/F3 and the parked "pre-computed grids" idea in the tracker go to Divine as an architecture change, not silently.

**Recorded production result (2026-10-16): the gate FAILS on the design as built.**

Source: Cloudflare Workers Logs through the observability API, which holds every request (`wrangler tail` dropped 9 to 10 of 25 events per run and could not supply 20 samples). Only spike requests that answered 200 are counted; the preparation request (204) and unrelated requests are excluded. CPU is whole milliseconds. Three runs from Divine's laptop, 60-match upload, free plan.

| Run | Worker version | Requests | p50 ms | p95 ms | max ms | First 5 requests ms | Above 6 ms | At or above 10 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 429647d4 | 25 | 5 | 22 | 27 | 22, 11, 12, 7, 4 | 10 | 6 |
| 2 | 429647d4 | 23 | 6 | 22 | 32 | 22, 32, 6, 18, 6 | 11 | 4 |
| 3 | 4bb7517b | 25 | 6 | 16 | 63 | 63, 10, 6, 6, 6 | 12 | 6 |
| All | | 73 | 6 | 22 | 63 | | 33 | 16 |

After the first 5 requests of each run: p50 5, 5, 4 and p95 13, 10, 14. So the typical warmed request sits around 3 to 9 ms with spikes to 13 to 16, and the first requests of a fresh isolate (right after a deploy or a quiet period) cost 22 to 63 ms.

**Reading:** p95 is 22 ms against the 6 ms target, and 16 of 73 requests (22%) used 10 ms or more, the Free plan limit. None failed: every invocation ended `ok` with HTTP 200. Cloudflare's limits page says an isolate has "some built-in flexibility" for infrequent overruns and terminates the Worker only if it "starts hitting the limit consistently". That slack is not something to design on: a real upload that lands on a cold isolate could be terminated with error 1102 (risk R-P1). The bot will mostly see the cold case, because uploads come about once a day.

**Caveat on the cold numbers:** the synthetic blobs and the Zod schema are part of the workload, and grammY is not. Both sides move the real figure, so the next step is a re-measure, not a conclusion about the final engine.

**Decision gate (essentials Stage 1, step 8):** p95 is above 6 ms, so F1 is applied and re-measured next (per-team rows instead of whole model blobs, a hand validator instead of Zod, precomputed factorial tables). F2 and F3 are not adopted. Because p95 is above 6 ms, the parked "nightly pre-computed grids" idea is handed to Divine in the tracker.

**Recorded production result after F1 (2026-10-16): the gate still FAILS, by a smaller margin.**

F1 as deployed in PR #7 (Worker version bd061009, bundle 23 KiB instead of 789 KiB): a hand validator replaces Zod, the Worker reads only the teams in the upload (per-team model rows), and Poisson probabilities use a recurrence instead of a factorial table. Outputs are unchanged (regression tests pin the pre-trim results; 1,500 mutated payloads give identical accept/reject decisions). Same method and filters as above: one run of the driver, 60-match upload, free plan, Workers Logs. The driver sent 40 requests, all HTTP 200; Workers Logs returned 39 of them (one invocation missing from the export).

| Set | Requests | p50 ms | p95 ms | max ms | At or above 10 ms |
|---|---|---|---|---|---|
| All | 39 | 3 | 16 | 22 | 4 |
| After the first 5 | 34 | 3 | 6 | 16 | 1 |

First 5 requests (ms): 22, 13, 9, 4, 12. Full series in order: 22, 13, 9, 4, 12, 4, 3, 6, 3, 3, 2, 5, 3, 3, 1, 3, 2, 4, 16, 4, 2, 4, 2, 4, 2, 2, 3, 1, 4, 1, 3, 2, 4, 2, 3, 2, 2, 5, 2.

Against the pre-F1 runs: p50 6 to 3 ms, p95 22 to 16 ms, requests at or above 10 ms 22% to 10%. The warmed typical request now sits at 2 to 4 ms. Two costs remain: the first few requests of a fresh isolate (22, 13, 9, 4, 12 ms, even though the preparation request ran first), and an occasional single spike (16 ms once in 34 warmed requests).

**Verdict:** ADR-013's gate (p95 at most 6 ms, no invocation near the 10 ms limit) is not met: p95 is 16 ms and the maximum is 22 ms. The 6 ms p95 is met only if the first five requests are discarded, and that is not the gate. Because the bot sees about one upload a day, nearly every real upload lands on a cold isolate, so the cold figure is the one that matters. F1 is exhausted. The remaining rungs, F2 (split across invocations), F3 (offload to Actions) and the parked "nightly pre-computed grids" idea, are architecture changes and go to Divine; none is adopted here.

**Caveats:** the spike leaves out grammY, D1 and Telegram subrequests (section above), so the real path costs more, not less. A sample of one run is small; the cold-start figure is the stable finding.

## 3. Tests run for Stage 1

| Suite | Command | Result at 2026-10-16 |
|---|---|---|
| Worker (Vitest, workerd, local D1 with the real migration) | `npm run test:bot` | 64 passed |
| Repo rules and tools (node:test) | `npm run test:scripts` | 41 passed |
| Python (pytest) | `cd apps/fit && python -m pytest` | 41 passed |
| Lint, format, types | `npm run lint`, `npm run typecheck`, `ruff`, `mypy --strict` | clean |
| Secret scan | `gitleaks detect --no-git` | no leaks (fake test values allowlisted by exact value in `.gitleaks.toml`) |

Mutation checks done by hand (each breaks one behavior and the suite must fail): auth compare always true, group chats allowed, dedupe always "first time", D1 parameter cap removed, client errors retried, resume key ignoring data. Every one was caught.

## 4. football-data.org v4 facts used by Stage 2 (checked against docs.football-data.org on 2026-10-17)

- `GET /v4/competitions/{id}/matches` filters: `season` (integer; the example `season=2021` is the 2021/22 season, so the start year), `dateFrom` and `dateTo` (`yyyy-MM-dd`, used together), `status`, `matchday`, `stage`, `group`. No maximum date range is documented; the nightly window is 10 days. `GET /v4/competitions/{id}/teams` takes `season`.
- Statuses: `SCHEDULED, TIMED, IN_PLAY, PAUSED, FINISHED, SUSPENDED, POSTPONED, CANCELLED, AWARDED`. The table accepts `IN_PLAY` for both `IN_PLAY` and `PAUSED`.
- Score: `duration` is `REGULAR`, `EXTRA_TIME` or `PENALTY_SHOOTOUT`. **`fullTime` is the final score and includes extra time and the shootout** (the docs' sample shows 7-6 for a penalty decision), so it is the 90-minute score only when `duration` is `REGULAR`. `regularTime` holds the goals after 90 minutes. This is exactly the ADR-010 rule implemented in `footy.reconcile`: `regularTime` first (`result_basis='regular'`), else `fullTime` when `duration=REGULAR` (`'ft_90'`), else `unverified` with NULL goals.
- Free plan: 10 requests per minute (we pace at 6.5 s). The docs do not say which seasons the free plan returns. A `403` means a restricted resource (paid subscription needed); the client reports it as "not available on this plan" and carries on.
- **Free-history depth:** not yet measured. Run the `bootstrap-dry-run` command; the report's `history_depth` shows `ok` or `restricted` per competition and season.
