# Verification record (Essentials 1, Stage 1)

What was verified, how, and what is still open. Numbers marked **indicative** are not the ADR-013 gate.

## 1. Verify-at-build items (architecture section 16)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | football-data.org free-history depth, fields, terms | **Open.** The register is now signed (2026-10-16). Fields and parameters are confirmed from the v4 docs (section 4). The free-history depth is settled by `footy bootstrap --dry-run` (workflow `data`, command `bootstrap-dry-run`); result goes in section 4 | `docs/legal/source_terms_register.md` section 1, section 4 below |
| 2 | football-data.co.uk terms for hand download; CSV headers | **Checked, not conclusive.** The site is "for private individuals" and "league match prediction only"; manual download is not addressed. CSV column headers are verified in Stage 2 against hand-written fixtures | Register section 2 |
| 3 | D1 REST batch support and the 100-bound-parameter limit | **Largely verified in production (2026-10-17).** The bootstrap sent batches of 10 statements with up to 100 bound parameters each and wrote 9,280 matches, 238 teams and 616 aliases without error. Batch atomicity and the exact limit are still not tested against the live service (`d1_probe` can do it: workflow `data`, command `d1-probe`). Earlier note: The OpenAPI spec accepts `{"batch": [...]}` and a single `{sql, params}`. The 100-parameter limit and batch atomicity are **not confirmed from documentation**; the live probe `python -m footy.repo.d1_probe` answers both once a real D1 exists. The client enforces 100 and is tested against a fake. | Cloudflare API spec, `d1_probe.py`, `tests/test_d1_probe.py` |
| 4 | Workers Logs retention; D1 Time Travel retention (Free) | **Workers Logs: 3 days on Free** (7 days from the 2026-12-01 observability pricing change). Pull `cpuTime` within 3 days of the spike. **Time Travel retention: not confirmed** in this session; check in the dashboard before the Stage 7 restore drill | Cloudflare docs, Workers pricing page |
| 5 | GitHub branch protection and environments on a private Free repo; 60-day auto-disable | **Branch protection and deployment protection: not available** for private repos on Free (search of GitHub docs, secondary sources agree). **Compensating controls are wired:** committed `pre-push` hook (tested against a real `git push`), `deploy.yml` merged-PR guard, `CF_DEPLOY_TOKEN` referenced only from `deploy.yml`. 60-day auto-disable: documented for public repos only; confirm once at the Stage 7 schedule check | `scripts/hooks/pre-push`, `scripts/verify-merged-pr.mjs`, `.github/workflows/deploy.yml` |
| 6 | soccernews.com terms | **Checked.** Personal, non-commercial use only; the system never reads the site | Register section 3 |
| 7 | Worker CPU of the real engine (ADR-013 spike) | **Measured in production: gate failed.** p95 22 ms, then 16 ms after the F1 trims (p50 3 ms, max 22 ms). Divine chose pre-computed grids (architecture ADR-037) | Section 2 |
| 8 | Pi-rating constants | **Verified in Stage 4 (2026-10-17), with one caveat**: lambda 0.035, gamma 0.7, b 10, c 3, psi(e) = 3 log10(1+e), every team starts at 0. See section 6 | Section 6 |

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
- **Free-history depth: MEASURED 2026-10-17 (dry run, workflow run 38957609206): the free plan returns all three seasons asked for (2024-25, 2025-26 and 2026-27) for all nine competitions.** 9,280 matches received, 8,771 usable, 509 skipped only because 15 club spellings were unknown (fixed in `data/aliases/fd_org.json`; no record was invalid, no anomaly, no outage). So the warm-up risk from a current-season-only free tier does not apply. Premier League, Serie A, Championship and the older seasons of most leagues mapped completely on the first try.

## 5. Stage 3: Dixon-Coles, scoring and the backtest (facts measured while building)

- **Grid tail (architecture section 8.1).** The text says the mass beyond 12 goals is below 1e-6 before renormalisation. Measured per side: 6e-8 at a rate of 1.8, 2e-7 at 2.0, 6e-7 at 2.2, 1e-6 at 2.3, 2.4e-6 at 2.5, 1.6e-5 at 3.0. So the claim holds for fixtures where each side's rate is up to about 2.3 goals, which covers almost every real match; above that the grid is still renormalised and still sums to 1. Test: `tests/test_grid.py::test_tail_beyond_twelve_goals_is_negligible_for_realistic_rates`.
- **Extreme-fixture guard.** A very strong side against a very weak one from different leagues can give rates near 5 and, with a positive fitted rho, a negative Dixon-Coles correction factor (this broke a backtest run in a test). `DcModel.grid` therefore clips each rate to 0.01..6 and clamps rho to the interval where every factor stays positive (`footy.models.grid.clip_rate`, `feasible_rho`). Inside the normal range it changes nothing. The golden vectors include a clamped and a clipped case so the TypeScript engine, if it ever ports this, must do the same.
- **Fit speed.** A synthetic league the size of production (about 6,700 matches, 100 teams) fits in about 1 s (375 L-BFGS-B iterations), so a 26-fold backtest with a 9-point sweep takes a few minutes on a GitHub runner.
- **Scipy typing.** scipy ships no type stubs; `mypy` ignores missing imports for `scipy.*` only (`pyproject.toml`). It is used only through `scipy.optimize.minimize`.
- **Golden vectors** live in `packages/contracts/golden/dc_grid_v1.json` (synthetic inputs, 169 cells, markets). Regenerate with `python -m footy.models.golden --write` from `apps/fit` with `PYTHONPATH=src`, then `npx biome format --write packages/contracts/golden`. `--check` (and a pytest) fails when the file differs from the code by more than 1e-12.
- **Running the backtest on the real data:** Actions, workflow `data`, command `backtest` (inputs `test_days`, `half_lives`, `shrinks`; defaults 365 days and a 3 x 3 sweep). The readable report is in the job log, the JSON summary is stored in `job_runs.summary_json` (kind `backtest`). The numbers it prints are **tuning on history, not validation**: the sweep picks starting values on the same matches it scores.
- **Real backtest result (production data, 2026-10-16/17; workflow run 38979043352, dc only, 3 x 3 sweep).** Test period 2025-10-17 to 2026-10-16, 23 folds of 14 days, 2,533 matches forecast (230 skipped under the 10-match rule). **Dixon-Coles mean 1X2 RPS 0.2044 against the league-frequency baseline's 0.2309** (skill 11.5%, paired difference -0.0264 +/- 0.0024). It beats the baseline in all nine competitions: BL 0.1909 vs 0.2308, CHA 0.2217 vs 0.2299, EPL 0.2161 vs 0.2288, ERE 0.1987 vs 0.2304, L1 0.2153 vs 0.2306, LL 0.2023 vs 0.2262, PPL 0.1667 vs 0.2294, SA 0.1991 vs 0.2368, UCL 0.2177 vs 0.2417. The half-life / shrinkage sweep is flat: all nine cells lie between 0.2041 and 0.2061; the best is half-life 200 with shrinkage 4 (0.2041), the default 300 / 4 gives 0.2042, so **the starting values were kept**. This run also showed 3 of 23 folds failing to fit (iteration cap of 500); fixed in PR #17 (cap 3000, tolerance 1e-10). **Stage 3 exit criterion met: Dixon-Coles beats the baseline.** Labelled tuning on history, not validation.

## 6. Stage 4: pi-rating constants (verify-at-build item 8), the models and the registry

**Pi-rating (Constantinou and Fenton, 2013, *J. Quantitative Analysis in Sports* 9(1), 37-50, doi 10.1515/jqas-2012-0036).** Read from the author's own PDF (`constantinou.info/downloads/papers/pi-ratings.pdf`) and cross-checked:

| Item | Value | Where it was confirmed |
|---|---|---|
| Initial rating of a new team | 0 ("the average team") | Paper section 2, text |
| Two ratings per team (home, away); one catch-up learning rate between them, one learning rate for new results | yes | Paper sections 2 and 3, text |
| Optimal learning rates on five EPL seasons | **lambda = 0.035, gamma = 0.7** | CRAN `piratings` package defaults (0.035 / 0.7) and the author's 2022 paper (Constantinou, arXiv 2003.09384), which cites "lambda=0.035 and gamma=0.7" from the 2013 paper |
| Error weighting | **psi(e) = 3 x log10(1 + e)** | The 2022 paper restates it as the 2013 function; the 2013 paper describes it as diminishing the weight of large goal differences |
| Expected goal difference against the average opponent | sign(R) x (b^(\|R\|/c) - 1), **b = 10, c = 3** | CRAN `piratings` defaults (b 10, c 3) and the paper's prose ("b is the base of the logarithm"). The paper's worked example (4-1 win, both teams' ratings fall because a bigger win was expected) matches this form |
| Update (home X, away Y) | H_X += lambda x psi_H; A_X += gamma x (change in H_X); A_Y += lambda x psi_A; H_Y += gamma x (change in A_Y), with psi_H = +psi(e) if the home side beat the predicted difference and -psi(e) otherwise, and psi_A = -psi_H | 2022 paper restates the structure; 2013 paper text lists the same four steps |

**Caveat.** In the PDF the equations are set in a symbol font and did not survive text extraction, so the exact formulas were not read as equations from the 2013 paper. The structure and constants come from its prose, the author's 2022 restatement and the maintained R implementation, and they agree with each other. My earlier recollection of "lambda 0.06, gamma 0.5" was wrong and is not used. The constants are tested against hand-computed updates (`tests/test_pi_rating.py`).

**Rating to grid (a hypothesis, GR-07 and ADR-006).** The paper predicts goal DIFFERENCES. The grid needs two rates, so: `lambda_home = max(0.05, (T + d)/2)`, `lambda_away = max(0.05, (T - d)/2)` with `T` the competition's recent mean total goals and `d = s x gD`. The scale `s` is fitted on the training window by regressing observed on predicted differences through the origin (clipped to 0.2..2). The backtest decides whether this is any good.

**Bivariate Poisson.** The analytic gradient uses the identity dP(x,y)/dlambda1 = P(x-1,y) - P(x,y) (likewise lambda2; lambda3 uses P(x-1,y-1)); checked against finite differences. A synthetic fit of 30 teams over 8 seasons (about 3,400 matches) takes 7 to 8 s, so a production-sized fit may take about 20 s (about 8 s after the log-factorial table replaced repeated `gammaln` calls, with the same objective and iteration count). On data generated from a bivariate Poisson it recovers team strengths about as well as Dixon-Coles does (correlation 0.91 vs 0.91) and the covariance within 0.02 to 0.03 of the truth (slightly low, from shrinkage).

**Ensemble weights.** `w = n/(n+50) x softmax(-kappa x mean RPS) + 50/(n+50) x prior`, with kappa = 100 (RPS differences between models are around 0.001 to 0.01, so a softmax with kappa 1 would be almost flat). The specification shrinks toward equal weights; until scored predictions exist it also says the initial weights come from the backtest, so `prior` is the backtest softmax when a `backtest` job summary exists in `job_runs` and equal weights otherwise. With no backtest this is exactly the specification. kappa, the 200-prediction window and the pseudo-count 50 are starting values, unvalidated.

**Promotion gate.** Structural checks plus the stability guard of ADR-030 (a bound of 0.5 on any team value, unvalidated). Both required fixtures are tested end to end: a corrupted run (payload altered, hash no longer matches) and a jumped-parameters run (one team moved by 2.0 with a valid hash) are rejected, recorded as `rejected` with every reason, and the previous run stays active. Every active team must have a `team_form` row (teams with no matches, such as the dropped Scottish clubs, get `n_training = 0`), otherwise the 95% coverage check could never pass.

**Atomicity.** Promotion is one batch of three guarded statements. D1's batch atomicity is documented but still not tested against the live service (item 3); the tests prove the guards hold on SQLite, including a failure injected mid-promotion.

**Operations (manual until `nightly.yml` exists in Stage 7).** Actions, workflow `data`: `backtest` (set `models` to `dc,pi,bp` and a single half-life and shrinkage for the full comparison), then `fit`, then `publish`. **Rollback:** `python -m footy.cli publish --rollback RUN_ID` (the workflow's `publish` command does not expose it; run it from a shell with the D1 token, or ask Claude Code to add a workflow input). Only a `superseded` run still inside the newest 30 can be rolled back to.

**Real results (production data, 2026-10-17).**

Clean three-model backtest after the optimiser fix (workflow run 38980767946: models `dc,pi,bp`, 365 days, half-life 300, shrinkage 4; no failed folds). 23 folds, 2,861 matches forecast, 230 skipped:

| Forecaster | RPS 1X2 | RPS totals | Log loss | Skill vs baseline | Paired RPS difference |
|---|---|---|---|---|---|
| Baseline (league frequencies) | 0.2304 | 0.0758 | 1.0737 | | |
| Pi-rating | 0.2076 | 0.0757 | 1.0115 | 9.9% | -0.0228 +/- 0.0026 |
| Dixon-Coles | 0.2042 | 0.0757 | 0.9981 | 11.4% | -0.0262 +/- 0.0022 |
| Bivariate Poisson | 0.2042 | 0.0756 | 0.9985 | 11.4% | -0.0262 +/- 0.0022 |
| **Ensemble** | **0.2040** | **0.0751** | 0.9975 | 11.5% | -0.0264 +/- 0.0023 |

Per competition (RPS 1X2; baseline / pi / dc / bp / ensemble): BL .2311/.1989/.1956/.1956/.1958, CHA .2300/.2268/.2204/.2204/.2209, EPL .2280/.2176/.2129/.2130/.2128, ERE .2294/.1970/.1968/.1970/.1964, L1 .2310/.2162/.2119/.2120/.2120, LL .2267/.2039/.2023/.2023/.2019, PPL .2285/.1774/.1761/.1763/.1759, SA .2358/.1991/.1988/.1988/.1983, UCL .2392/.2238/.2121/.2119/.2097.

What this does and does not show:
- **Every model and the ensemble beat the baseline overall and in all nine competitions.** The pi-rating mapping (a hypothesis, GR-07) works, but it is the weakest of the three.
- **Dixon-Coles, bivariate Poisson and the ensemble are tied for practical purposes.** The gaps between them (0.0002) are far smaller than the standard error of the paired difference against the baseline (0.002), so none of the three can be called better than another on this evidence. The ensemble is nominally best overall; its clearest edge is UCL (0.2097 vs 0.2119 and 0.2121), the weakest-identified league link (ADR-007), where only 120 matches were forecast.
- The totals RPS is almost identical for all forecasters, so the models add little over league frequencies for total goals; the 1X2 market is where they help.
- **Not a validation.** The windows overlap the data used to choose the starting values; half-life, shrinkage, kappa and the stability bound are still unvalidated starting values. The product's success metric (beat the baseline over at least 300 logged live predictions) is measured later from the prediction log.

First real `fit` (run 38981127749) and `publish` (run 38981213952): all three models `ok`, no failures; 225 `team_form` rows; 6,813 matches in the window; ensemble weights from the backtest prior (kappa 100): bp 0.368, dc 0.369, pi 0.263; the gate passed on the first run (models ok, all payload hashes verified on re-read, team_form coverage 1.0; the stability guard had no previous run to compare with) and **run `R20261016T232312Z` is the active run**. Not yet exercised on the live service: a second publish with the stability guard against a real previous run, and a rollback.

**Review fixes (2026-10-17, after the code review of Stages 3 and 4).** All nine findings and the missing drift override were repaired; the tracker has the list. Two measurable effects: the bivariate Poisson fit is about twice as fast, and the shared-covariance floor no longer inflates a small fitted lambda3. **The backtest numbers above were produced before these fixes**; two of them can move slightly (the ensemble row, because its weights now use aligned histories, and any bivariate Poisson row with a very small covariance). Re-run the three-model backtest after merging to refresh them; no conclusion is expected to change.

