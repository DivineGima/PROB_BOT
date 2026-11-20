# PROB_BOT: Football Reliability Screener and Probability Bot

A private Telegram bot that estimates football probabilities. You send it the list of matches your
screener has approved; it replies with the chance of a home win, a draw and an away win, and the
chance of over 0.5 to 5.5 total goals, for each match. It checks its own accuracy over time and sends
you a weekly report.

> Probabilities, not advice. The bot never tells you what to bet on.

**Status:** Stages 1 to 7 are built, reviewed and deployed (see `tracker/`). The remaining steps are the
go-live checks in [docs/runbook.md](docs/runbook.md), section 8.

## Contents

1. [How it works](#how-it-works)
2. [Using it every day](#using-it-every-day)
3. [Reading a reply](#reading-a-reply)
4. [The screener file](#the-screener-file)
5. [What runs by itself](#what-runs-by-itself)
6. [When something goes wrong](#when-something-goes-wrong)
7. [One-time setup](#one-time-setup)
8. [Project layout](#project-layout)
9. [Working on the code](#working-on-the-code)
10. [Secrets](#secrets)
11. [Documentation map](#documentation-map)
12. [Limits](#limits)

## How it works

Two programs, one small database:

```
 every night (GitHub Actions, Python)            when you upload (Cloudflare Worker, TypeScript)
 ───────────────────────────────────            ──────────────────────────────────────────────
 results + fixtures  ──►  3 models               your .json  ──►  check the file
 (football-data.org)      (dc, pi, bp)                              │
          │                    │                                    ▼
          ▼                    ▼                          look up the stored forecasts
   score old predictions   blend into one forecast                  │
          │                    │                                    ▼
          └──────────►  stored forecasts for the   ◄────────  log the prediction, reply in Telegram
                        next few days (Cloudflare D1)
```

- **The nightly job** does all the maths. It fits three models (Dixon-Coles, a pi-rating model and a
  bivariate Poisson model), blends them with weights based on how well each has done lately, and stores
  a finished forecast for every upcoming fixture. A new set of numbers goes live only if it passes its
  safety checks (models fitted, data intact, nothing jumping unreasonably, forecasts present).
- **The Worker** never calculates a probability. It validates your file, looks the match up in the
  stored forecasts, writes the first prediction for each match to a log (that first prediction is never
  changed), and replies. This keeps it fast enough for Cloudflare's free plan.
- **Scoring:** after a match is played, its logged prediction is scored (RPS for 1X2 and for goals,
  log loss, Brier). The weekly report compares the results with a simple baseline.
- **Alerts:** if the nightly job fails, the numbers go stale, forecasts are missing or an upload gets no
  reply, you get a Telegram message.

Design details: [system_architecture/system_architecture_3.md](system_architecture/system_architecture_3.md).

**Planned (version 3, not built yet):** read-only bot commands (`/status`, `/fixtures`, `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team`, `/alerts`, `/help`). Until Stage 8 is built, any text message still gets the one-line usage hint.

## Using it every day

About two minutes:

1. Run your screener and save its `.json` file.
2. In Telegram, send the file to the bot **as a document** (paperclip, then File).
3. Wait about 10 seconds for the reply and read it (next section).
4. Nothing else. Alerts and the weekly report arrive by themselves.

Sending the same file twice is safe: matches already logged come back with the same numbers marked
`[already logged]`. If the bot does not answer, send the file again. If a text message is sent instead
of a file, the bot answers with a one-line reminder.

## Reading a reply

```
EPL  Leeds United vs Manchester United   18 Oct 13:00 UTC (18:30 IST)
1X2   H 44.0%  D 25.6%  A 30.4%
Over  0.5 93.3 | 1.5 75.7 | 2.5 51.2 | 3.5 29.1 | 4.5 14.1 | 5.5 5.9   (Under = 100 - Over)
Models dc+pi+bp   w 0.37/0.26/0.37   Drift: stable (goals only)
```

| Part | Meaning |
|---|---|
| `H D A` | Chance of a home win, a draw, an away win. They add up to 100% |
| `Over 2.5` | Chance of 3 or more goals in the match. Under is 100 minus Over |
| `Models dc+pi+bp  w ...` | The three models behind the number and how much each counts |
| `Drift: stable` | Recent form is in line with the season, so the number can be trusted |
| `Omitted:` | Matches that got no numbers, each with a reason (below) |
| Footer | The model run used, how many matches were published, omitted or excluded by the screener |

| Omission reason | Meaning |
|---|---|
| `DRIFT` | A team's recent goals for or against moved too far from its season average; the bot will not guess |
| `INSUFFICIENT_HISTORY` | A team has fewer than 10 matches of history |
| `NO_FORECAST` | The match is not in the stored forecasts (a fixture the nightly job did not load) |
| `NO_MODEL` | No model could produce a forecast for it |
| `DATE_MISMATCH`, `STARTED`, `TOO_FAR` | The kickoff is not on the file's date, has already started, or is more than 48 hours away |
| `DUPLICATE_PAIR` | The same fixture appears twice |

A banner **STALE MODELS** means the stored numbers are more than 36 hours old; check the nightly job.

## The screener file

A `.json` document, at most 256 KB, with `schema_version` 1. Unknown extra fields are ignored; a
missing or wrong field is rejected with a short message naming it.

| Field | Rule |
|---|---|
| `schema_version` | `1` |
| `run_date_utc` | The date of the matches, `YYYY-MM-DD` |
| `notes` | Text of at most **2,000 characters**, or `null` |
| `matches` | Up to 100 matches. Each has `match_id`, `competition` (EPL, LL, BL, SA, L1, UCL, ERE, PPL, CHA or SPL), `home`, `away` (the club names as the bot knows them), `kickoff_utc` (`YYYY-MM-DDTHH:MM:00Z`), `lineup_status`, `absences_home`, `absences_away`, `rest_days_home`, `rest_days_away`, `source_urls` |
| `excluded` | Up to 200 `{match, reason}` entries for matches the screener rejected. Start `reason` with its gate code (`G1` to `G6`, for example `G2_EARLY_SEASON`) so the bot can count them by gate |

The machine-readable contract is [packages/contracts/screener_v1.schema.json](packages/contracts/screener_v1.schema.json).

## What runs by itself

| What | When | Where |
|---|---|---|
| **nightly**: ingest, score, fit, publish, (Monday) weekly report, health check, send alerts | 01:17 UTC (06:47 IST) | [nightly workflow](https://github.com/DivineGima/PROB_BOT/actions/workflows/nightly.yml) |
| **Watchdog**: alerts if no run is published, the run is stale, forecasts are missing, or an upload was never answered | every 6 hours | Cloudflare Worker cron |
| **backup**: export of the database, kept 30 days | Sundays 02:43 UTC | [backup workflow](https://github.com/DivineGima/PROB_BOT/actions/workflows/backup.yml) |
| **backtest**: re-checks the models on past matches; red means a model got worse | the 1st of each month | [backtest workflow](https://github.com/DivineGima/PROB_BOT/actions/workflows/backtest.yml) |
| **deploy**: publishes merged code and applies database migrations | every merge to `main` | [deploy workflow](https://github.com/DivineGima/PROB_BOT/actions/workflows/deploy.yml) |

The nightly schedule is off until the repository variable `NIGHTLY_ENABLED` is set to `true`.
You can also run any job by hand from the [data workflow](https://github.com/DivineGima/PROB_BOT/actions/workflows/data.yml)
(choose a command: `ingest`, `fit`, `publish`, `score`, `report`, and so on).

## When something goes wrong

Alerts arrive in Telegram. The full table, with one action for each, is in
[docs/runbook.md](docs/runbook.md). The common ones:

| You see | Do this |
|---|---|
| The bot does not reply | Send the file again. If it still does nothing, check the Worker's bot token (runbook, section 5) |
| Every match says `NO_FORECAST` | Run `ingest`, then `fit`, then `publish` from the data workflow |
| STALE MODELS, or an alert that the run is old | Run the nightly workflow by hand; check `NIGHTLY_ENABLED` |
| An alert that the nightly job failed | Open the link in the alert, read the red step, run the workflow again |
| A run was rejected | The old numbers stay live. Read the reasons in the alert before doing anything else |

Other drills (rollback of a model run, rotating a secret, restoring the database from a backup) are in the runbook.

## One-time setup

1. Create the Telegram bot, the Cloudflare account and database, and the GitHub secrets: [docs/setup.md](docs/setup.md).
2. Football-data.org may be used only after the terms entry is signed: [docs/legal/source_terms_register.md](docs/legal/source_terms_register.md).
3. After the first deploy: add the Worker secret `TELEGRAM_BOT_TOKEN` (`npx wrangler secret put TELEGRAM_BOT_TOKEN` in `apps/bot`) and the GitHub secret `TELEGRAM_CHAT_ID`.
4. From the data workflow run `ingest`, `fit` and `publish` once, so the bot has forecasts.
5. Run the nightly workflow by hand once, then set `NIGHTLY_ENABLED` to `true`
   ([Settings, Variables](https://github.com/DivineGima/PROB_BOT/settings/variables/actions)).
6. Work through the go-live checklist in [docs/runbook.md](docs/runbook.md), section 8.

## Project layout

```
apps/
  bot/            Cloudflare Worker (TypeScript): webhook, upload check, forecast lookup, reply, watchdog
  fit/            Nightly job (Python 3.12): ingest, models, forecasts, scoring, report, alerts (package `footy`)
db/migrations/    Database schema, forward-only SQL migrations (applied on deploy)
packages/contracts/   Screener file schema and numeric regression vectors
scripts/          Repo checks (SQL location, secret readers, no data files, migration lint) and deploy helpers
data/             Reference team and alias lists (no raw source data is ever committed)
docs/             Setup, runbook, verification record, legal register
prd/              Product requirements, versioned (PRD_N)
system_architecture/   Architecture and decision log, versioned
essentials/       Build plan per version, with its stages
tracker/          Dated build log, appended after every working session
claude.md         The rules the coding agent follows in this repository
.github/workflows/    ci, deploy, nightly, backup, backtest, data
```

## Working on the code

Requirements: Node 24 or newer (see `.nvmrc`) and Python 3.12.

```bash
npm ci                        # TypeScript dependencies
npm run lint                  # Biome
npm run typecheck             # tsc for the Worker and the scripts
npm test                      # Worker tests (Vitest on a local D1) and script tests
npm run check:repo            # SQL stays in repo/, secrets read only by auth/ and telegram/, no data files, migrations

cd apps/fit
python -m pip install --require-hashes -r requirements-dev.txt
python -m ruff check . && python -m ruff format --check .
python -m mypy --strict src tests
python -m pytest              # the models, the whole nightly job on a fake database, the CLI
```

The nightly job's commands (`python -m footy.cli <command>`, with `PYTHONPATH=src`):

| Command | What it does |
|---|---|
| `bootstrap` | Seeds teams and aliases and loads the last seasons of results |
| `ingest` | Fetches new results and fixtures |
| `fit` | Fits the three models, blends them and stores a forecast per fixture (a `building` run) |
| `publish` | Runs the promotion gate and makes the run live (`--rollback RUN_ID` goes back to an older one) |
| `score` | Settles logged predictions against results |
| `report` | The weekly accuracy summary (`--send` posts it to Telegram) |
| `healthcheck` | Asks five questions about the system's state; raises alerts for failures |
| `alert` | `--flush` sends pending alerts; `--text` sends one message |
| `backtest` | Walks forward over past matches to compare the models with a baseline |

Rules for changes (details in `claude.md`):
- Work on a branch, open a pull request, never push to `main`. Merging to `main` deploys.
- Migrations only add; nothing is renamed or dropped in the change that replaces it.
- SQL lives only in `apps/bot/src/repo` and `apps/fit/src/footy/repo`, with bound parameters.
- No secrets, tokens or raw data dumps in the repository; tests use synthetic data.
- Add a dated entry to `tracker/` after each working session.

## Secrets

Names only; the values live in GitHub (Settings, Secrets) or Cloudflare (`wrangler secret put`), never in code.

| Secret | Where | Used by |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Worker secret and GitHub | The Worker's replies and alerts; the report and alert steps |
| `TELEGRAM_CHAT_ID` | GitHub | Where the report and alerts are sent (your own chat id) |
| `TELEGRAM_WEBHOOK_SECRET`, `WEBHOOK_PATH_SECRET` | Worker secret and GitHub | Proving a request really comes from Telegram |
| `ALLOWED_CHAT_ID`, `ALLOWED_USER_ID` | Worker secret | Only your chat may use the bot |
| `FD_ORG_TOKEN` | GitHub | football-data.org; only the ingest step sees it |
| `CF_ACCOUNT_ID`, `D1_DATABASE_ID`, `CF_D1_TOKEN` | GitHub | The nightly job's database access (database only) |
| `CF_DEPLOY_TOKEN` | GitHub | Used only by the deploy workflow |
| `WORKER_URL` | GitHub | Webhook registration and the deploy smoke test |

## Documentation map

| File | What is in it |
|---|---|
| [docs/runbook.md](docs/runbook.md) | Daily ritual, alert table, rollback, rotation and restore drills, go-live checklist |
| [docs/setup.md](docs/setup.md) | First-time setup steps and the checklists for each stage |
| [docs/verification.md](docs/verification.md) | What was measured live: CPU, reply time, backtests |
| [prd/PRD_3.md](prd/PRD_3.md) | What the product must do and why |
| [system_architecture/system_architecture_3.md](system_architecture/system_architecture_3.md) | How it is built, the decision log (ADRs), risks |
| [essentials/system_architecture_essential_2.md](essentials/system_architecture_essential_2.md) | The build plan for Stages 5 to 7 (built) |
| [essentials/system_architecture_essential_3.md](essentials/system_architecture_essential_3.md) | The build plan for Stage 8, the read-only bot commands (next) |
| [tracker/](tracker/) | The dated log of what was built, tested and decided |

## Limits

- It covers ten competitions: the Premier League, La Liga, Bundesliga, Serie A, Ligue 1, the Champions
  League, Eredivisie, Primeira Liga, the Championship and the Scottish Premiership.
- A team needs at least 10 recent matches of history to be forecast.
- Forecasts exist only for fixtures in the next few days that the nightly job has loaded.
- The models use goals only: no player or lineup data, no odds.
- The Worker's CPU time per upload is above the original 6 ms target (about 5 to 8 ms warm, up to about
  17 ms on the first request after a quiet spell). No request has failed; see the decision record
  ADR-048 in the architecture.
- The accuracy figures mean little before about 300 scored predictions.
- One user: the bot answers only the allowlisted chat.
