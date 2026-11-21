# Football Reliability Screener and Probability Bot — PRD

Oct 15, 2026 · @Divine Gima Folabit

**Version 4 — 2026-11-21.** A full snapshot of `PRD_3.md` plus the version-4 changes listed in the changelog below (visual Telegram messages, the strongest call, the daily results picture). Passages changed in version 4 are tagged **[v4]**. Written by Claude Code at your instruction on 2026-11-21 after you approved the mockups on your phone.

**Version 3 — 2026-11-21.** A full snapshot of `PRD_2.md` plus the version-3 changes listed in the changelog below (read-only bot commands). Passages changed in version 3 are tagged **[v3]**; the older **[v2]**, **[Rev-1]** and **[Rev-2]** tags are kept so the history stays readable. Written by Claude Code at your instruction on 2026-11-21 ("create the PRD, the architecture, the essentials and the tracker" for the bot commands); the command list and the verdicts-only rule for `/fixtures` are your decisions of the same day.

**Version 2 — 2026-10-17.** A full snapshot of `PRD_1.md` (with its Rev-1 to Rev-4 amendments folded in) plus the version-2 changes listed in the changelog below. Changed passages are tagged **[v2]**.

> **Storage note (added by System Designer, not PRD content):** Saved verbatim as `PRD_1.md`. Only two mechanical edits were made to the pasted text: (a) section headings were numbered 1–12 so the PRD's own references ("section 3", "section 7", "section 9", "section 11") resolve, and (b) the "Canonical team names" table, which was empty in the paste, was filled from the earlier draft that Divine supplied. Plain-text tables were converted to Markdown tables. No wording was changed.

> **Amendment note (Rev-1, 2026-10-16):** After the engineering review of this version, the PRD was amended in place at Divine's explicit instruction (an exception to the rule against in-place edits). Changed lines are tagged **[Rev-1]**. The version number stays 1. What changed: drift is goals-only in v1 (shots later); history-only clubs are kept; an unanswered upload raises an alert; predictions with no result are closed after 3 days; the source-terms check happens during build step 1; the Champions League final is treated like any match. See `system_architecture_1.md` section 18 for the full list. **Rev-2 (same day):** Divine's decisions on A-1 to A-4 are recorded: hand-downloaded football-data.co.uk files (or football-data.org only if not allowed, dropping the Scottish Premiership), two Cloudflare tokens, nightly run at 01:17 UTC, 30-second reply target.

## Changelog

### v4 — 2026-11-21: visual messages and the strongest call

**What changed**

1. **Every Telegram message is visual.** Upload replies and all ten commands use emoji bars (10 cells), status icons and short labels instead of rows of numbers. Still plain text: no Markdown, so nothing can fail on escaping.
2. **A favourite label per match:** 💪 clear favourite (60%+), 👍 slight favourite (50-60%), 🤷 open game (under 50%).
3. **The strongest call per match:** the one outcome the bot is most sure of among home, draw, away and over/under 1.5, 2.5 and 3.5 goals (the near-certain 0.5, 4.5 and 5.5 lines are left out). Ties go to the earlier one in that order. It is worded "most likely", never "best bet": the bot still gives no betting advice and uses no odds. It is worked out from the stored probabilities when shown, never stored, so old predictions get one too and nothing logged changes.
4. **Tracked:** `/results`, `/logged`, the daily picture and the weekly report show whether the favourite and the strongest call came true; the weekly report counts both, the favourite by label.
5. **A daily results picture:** after the nightly scoring, one picture (up to 12 matches each) of the predictions graded since the last one, sent only when something new was graded.
6. **The weekly report** is rewritten in plain words, and its chart becomes four panels: accuracy against the benchmark, how often the calls came true, goals said against happened, results said against happened.

**Unchanged:** the models, the maths, the data sources, the upload flow and its checks, the screener file, security (no new secret), legal, cost ($0), the success metric. `/fixtures` still shows verdicts only.

**Downstream Impact:** IMPACT. Architecture version 4 (ADR-053 to ADR-057) and Essentials 4 (Stage 9) follow, in `system_architecture_4.md` and `system_architecture_essential_4.md`. No database change.

### v3 — 2026-11-21: read-only bot commands

**What changed**

1. **Bot commands (replaces "no bot commands in v1").** From your chat only, the bot now answers ten read-only commands: `/help` (also `/start`), `/status`, `/fixtures`, `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team` and `/alerts` (section 7). They show what is already stored: the health of the model run and the nightly job, the verdicts stored for upcoming fixtures, the predictions already logged and their results, the latest weekly report, the outcome of the last upload, a team's goals form and the recent alerts. Reason: today any text message gets one fixed line, so checking the system means opening GitHub or waiting for an alert or the Monday report.
2. **`/fixtures` shows verdicts only, never probabilities** (your decision, 2026-11-21). Probabilities still come only from an uploaded screener file, so the screener's gates G1 to G6 always apply before you see a number, and every number you see is logged and scored. `/logged` and `/results` show only predictions that were already logged by an upload.
3. **Commands change nothing.** They never log a prediction, never start or stop a job and never switch a model run. Commands that would (re-run the nightly job, roll back, publish, void a prediction) are left out; the GitHub Actions tab stays the place for them. Reason: such a command would need a GitHub or Cloudflare token inside the bot, and one mistyped message could change the live models or the calibration record.
4. **Telegram's "/" menu** lists the commands, in your chat only.
5. **The usage hint gains a line:** "Send /help to see the commands."

**Unchanged:** the upload flow and its reply, the models, the nightly job, the grid and market definitions, the drift rule, the 10-match rule, the screener file contract, security (the same three checks guard commands), the data sources, legal, cost ($0), the success metric.

**Downstream Impact:** IMPACT. Architecture version 3 (a read-only command layer in the Worker, new decisions and threat rows) and Essentials 3 (a new Stage 8, bot commands) must follow. Both are done in `system_architecture_3.md` and `system_architecture_essential_3.md`. No database change is needed.

### v2 — 2026-10-17: probabilities are computed overnight and stored; the bot looks them up

**What changed**

1. **Where the numbers are computed (replaces the "bot computes grids" design).** The nightly job, which already fits the three models, now also computes the probabilities for every scheduled fixture in the next few days and stores them, together with the history and drift verdict, in the database. On upload the bot validates the file, finds each match in that stored set and replies. The bot does no model arithmetic. Reason: the Stage 1 measurement on the real Worker showed the arithmetic could not fit the free plan's CPU limit (p95 16 ms against a 6 ms target after the planned trims; the free limit is 10 ms), and uploads arrive about once a day, so nearly every upload starts a cold Worker. You chose this direction on 2026-10-16 (architecture ADR-037).
2. **A match with no stored forecast is omitted, with a new reason, `NO_FORECAST`.** The bot never computes a number itself as a fallback. This happens when the screener lists a fixture the nightly job did not know about (a fixture added or moved after last night's run, or one outside the forecast window).
3. **The Scottish Premiership is not predicted in v1** (decision A-1, path 2, 2026-10-16): football-data.org is the only source and does not cover it. The competition stays in the list so the club table stays whole; its matches are omitted as insufficient history, and the screener prompt stops listing it.
4. **Weights and the weekly report.** The ensemble weights now use the real rolling scores of logged predictions as soon as they exist (section 5), and a weekly report is sent to you on Mondays (build step 5).

**Unchanged:** the models, the grid and market definitions, the drift rule, the 10-match rule, the screener file contract, the reply format, security, legal, cost ($0), the success metric.

**Downstream Impact:** IMPACT. Architecture version 2 and Essentials 2 must follow: Stages 5 and 7 of the old build plan change (no TypeScript model code in the Worker; a forecast table and a forecast step in the nightly job), and the prediction log gains the stored forecast values. Both are done in `system_architecture_2.md` and `system_architecture_essential_2.md`.

## 1. Summary

This PRD adds the final tech stack and settles the Telegram hand-off: the Claude Project outputs a .json file, and the bot takes it as a file upload. Everything else carries over unless marked below.

What changed since the first draft:

- Tech stack added (section 3): TypeScript Cloudflare Worker for the bot, Python on GitHub Actions for model fitting, Cloudflare D1 for storage.
- Hand-off changed from pasted JSON to file upload. Telegram text messages cap at 4,096 characters, and my estimate is 250 to 800 characters per match, so a busy day would not fit in one message.
- Private GitHub repo and a two-language build (Python and TypeScript) confirmed by you.
- Verify-at-build checklist added (section 11) for facts I could not confirm during planning.
- **[v3]** Read-only bot commands (sections 6 and 7): the bot shows stored state on request; it still gives probabilities only for an uploaded file.
- **[v4]** Visual messages, the strongest call per match and a daily results picture (changelog v4).

## 2. Problem and target user

A personal, $0 system that screens daily fixtures for input reliability and returns probabilities for 1X2 and total-goals lines across 10 competitions. It gives probabilities only, never betting tips.

### Problem

- Short-run form is mostly noise: five-match windows have wide error bars, and real trends need roughly 20 to 30 matches (source: a player-stats education site, so a rough guide only).
- Predicted lineups, rotation, manager changes and early-season samples all weaken a model's inputs.
- Free data is uneven: football-data.org's free tier has no xG, no odds and no Europa League, and delays scores.
- No model guarantees correct predictions. Value comes from calibrated probabilities on matches whose inputs are reliable.

### Target user

One user: you, for personal use only. The system is not shared, published or redistributed.

- Outputs are probabilities with no bet picks, framed as analytics rather than tips, because of India's Public Gambling Act.
- If anyone else ever uses it, get legal advice first. This PRD is not legal advice.
- You build it yourself with Claude Code.

## 3. Final tech stack

Telegram is the only interface, a TypeScript Worker runs the bot, and Python on GitHub Actions fits the models. All of it runs at $0 on free tiers, which you must verify at build time because limits can change.

| Layer | Choice | Why |
|---|---|---|
| Frontend | None. Telegram is the interface. An optional static calibration dashboard on Cloudflare Pages can wait for v2 | A custom UI adds cost and attack surface for a one-user tool |
| Bot backend | TypeScript Cloudflare Worker (webhook mode) and Zod. **[v2]** Plain `fetch` calls to the Telegram Bot API instead of grammY | **[v2]** The bot only validates a file, looks up stored forecasts and renders the reply; it does no model arithmetic (the Stage 1 test showed that arithmetic did not fit the free CPU limit). Zod enforces schema version 1. grammY was dropped to save CPU and a dependency (the architecture's own trim step F1 allows it) |
| Model fitting | Python on a scheduled GitHub Actions job: numpy, scipy, pandas. penaltyblog is a candidate for Dixon-Coles, bivariate Poisson and Ranked Probability Score (unverified). The pi-rating is a custom build from the Constantinou and Fenton paper | Your PRD already finds Python Workers unclear for scientific libraries, so heavy fitting stays off the Worker. A Python and TypeScript split has real precedent |
| Database | Cloudflare D1 (SQLite): prediction log, model parameters, results | Sits next to the Worker with no extra service. Actions writes to it through Cloudflare's API |
| Authentication | No accounts. Telegram chat-ID allowlist plus Telegram's webhook secret-token header. Secrets live in Worker and GitHub secrets. **[Rev-2]** Two Cloudflare API tokens: the nightly job's is scoped to D1 only; a separate deploy token is used only by the deploy workflow | One user, so identity is a single chat ID. Least-privilege tokens limit damage if one leaks |
| APIs | football-data.org v4, football-data.co.uk CSV files (downloaded by hand and loaded, never fetched automatically **[Rev-2]**), Telegram Bot API (webhook and file download) | Fixed by your PRD. The Claude Project has no API link, so that hand-off stays manual |
| Testing | Vitest with the Workers test pool for the bot; pytest for the models. Tests that probabilities sum to 1, Zod fixtures, and a walk-forward backtest as a regression check | Catches the failures that matter here: inconsistent grids, bad schemas, and calibration drift |
| Deployment | Wrangler deploy from GitHub Actions, plus a cron workflow at 01:17 UTC (a non-round minute, because GitHub can delay jobs at the top of the hour) **[Rev-2]**. A final step sends a Telegram alert on failure | One repo, one CI system, no servers to run |

### Rejected alternatives

- Supabase for the database: my understanding is that free projects can pause when inactive, which would break a daily job. Verify before relying on this.
- Fitting inside a Python Worker: scientific-library support on Python Workers is unclear, and sources conflict.
- A web frontend: not needed while Telegram is the only interface.

## 4. Architecture and daily flow

The nightly job is the only thing that fits models and computes probabilities. **[v2]** The morning upload looks up the probabilities the nightly job already stored and logs each prediction, so the Worker stays light.

### Daily flow

1. At 01:17 UTC (06:47 IST) a scheduled job adds finished results to the log, then refits and re-scores the models. **[v2]** It then computes and stores the probabilities, history check and drift verdict for every scheduled fixture in the next few days.
2. At 08:00 IST you send "run today" in the Claude Project.
3. Claude lists the day's fixtures, applies the gates and outputs a .json file.
4. You upload the file to the Telegram bot as a document.
5. The bot downloads and validates it, finds each match among the stored forecasts (which already carry the history check and the drift verdict) and replies with 1X2 and over/under 0.5 to 5.5. **[v2]** A match with no stored forecast is omitted with its reason.
6. The bot logs each prediction (the first prediction for a fixture is kept and never changed).
7. **[v3]** At any time you can send a command (for example `/status` before the upload, or `/fixtures` to see which matches have a stored forecast). Commands only read; they change nothing.

## 5. Decisions made

The hand-off and the whole stack are now decided. "Decided" means you chose it in this chat. "Default" means you asked me to fill it in, so it is my pick and easy to change. Rows marked New or Changed differ from the first draft.

| Area | Decision | Status |
|---|---|---|
| Users | You only | Decided |
| Budget | $0, free serverless hosting on Cloudflare | Decided |
| Competitions (10) | Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, Eredivisie, Primeira Liga, Championship, Scottish Premiership | Decided |
| Europa League | Not screened in v1 (no verified free data source). It still counts toward the rest and early-season gates | Decided |
| Events | 1X2 and total-goals over/under at 0.5, 1.5, 2.5, 3.5, 4.5, 5.5. No BTTS, correct score, corners or cards | Decided |
| Drift measure | Goals-based, no xG. **[Rev-1]** v1 uses goals only; shots are added later, after the football-data.co.uk decision, because shots come only from that source | Decided |
| Drift thresholds | Launch with starting values labelled "unvalidated" until backtested | Decided |
| Models | Dixon-Coles, a cross-league Elo or pi-rating, and bivariate Poisson, combined as an ensemble | Decided |
| Ensemble weighting | Weights from rolling Ranked Probability Score; if a model fails to fit, run the rest and flag it | Default |
| Re-evaluation | Before each daily batch of matches | Decided |
| Training history | Last 3 seasons with time decay | Decided |
| Prediction log | Save every prediction and its result to track calibration | Decided |
| Daily trigger | You send "run today" in the Claude Project each morning at 08:00 IST | Decided, time is a default |
| Model fitting | Scheduled GitHub Actions job at 01:17 UTC (06:47 IST), before your run | Default |
| Hand-off (Changed) | The Project outputs a .json file; you upload it to the Telegram bot as a document. No pasted JSON | Decided |
| Project sources | Official league and UEFA sites for fixtures, soccernews.com injuries pages for absences (see the appendix) | Default, terms unverified |
| Bot commands (**[v3]**) | Ten read-only commands from your chat (section 7); `/fixtures` shows verdicts only; no command changes anything | Decided (2026-11-21) |
| Forecast timing (**[v2]**) | Probabilities are computed by the nightly job for fixtures in the next few days and stored; the bot only looks them up. A fixture without a stored forecast is omitted as `NO_FORECAST`, never computed in the bot | Decided (2026-10-16) |
| Pipeline sources | football-data.org for fixtures and results. **[Rev-2]** football-data.co.uk (history and the Scottish Premiership) from files you download by hand and load, never fetched automatically. If hand downloading is not allowed (checked in build step 1): football-data.org only, and the Scottish Premiership is dropped | Decided; terms checked in build step 1 |
| Claude's reading | Dropped from v1; the bot can't call Claude's API at $0 | Default |
| Failure alerts | A Telegram message to you when the job or bot fails | Default |
| Success metric | Beat a league-average-frequency baseline on Ranked Probability Score over at least 300 logged matches | Default |
| Build | You, with Claude Code | Decided |
| Repository (New) | Private GitHub repo | Decided |
| Languages (New) | TypeScript for the bot, Python for model fitting | Decided |
| Stack (New) | Cloudflare Worker with grammY and Zod; GitHub Actions with Python; Cloudflare D1; Vitest and pytest; Wrangler deploys. Details in section 3 | Decided |

## 6. Core features

Six features, with the Telegram bot changed to take a file instead of pasted text.

1. **Match screener (Claude Project).** Reads only your listed sources, applies the gates in section 7 and outputs a .json file for matches that pass, plus an excluded list with reason codes. It never outputs probabilities, odds or opinions on who will win.
2. **Drift filter (nightly job, shown by the bot).** **[v2]** Compares each team's last 10 matches with its season average for goals scored and conceded. **[Rev-1]** v1 uses goals only; shots are added later as a separate change once the football-data.co.uk decision is made. A match counts as stable only inside a threshold that starts as an unvalidated value.
3. **Probability engine (nightly job).** Builds a scoreline grid per match, then derives 1X2 and over/under 0.5 to 5.5 from that one grid so the events stay consistent. **[v2]** The grid is built in the nightly job; the bot stores and shows the derived numbers.
4. **Ensemble with pre-batch re-evaluation (fitting job).** Refits and re-scores Dixon-Coles, the cross-league rating and bivariate Poisson before each daily batch, then combines them.
5. **Telegram bot.** Accepts the uploaded .json document from your chat only and replies with probabilities per match. **[v2]** The bot replies from the stored forecasts. **[v3]** It also answers read-only commands (section 7) that show the stored state: health, upcoming verdicts, logged predictions and results, the weekly report, the last upload, team form and alerts.
6. **Prediction log and calibration.** Stores every prediction and its result, and reports Ranked Probability Score, log loss and calibration curves, with walk-forward backtesting.

## 7. Requirements

Requirements are unchanged except for the input path and the stack-related lines.

### Screener gates

All values are starting points, unvalidated until backtested.

| Code | Match is excluded when |
|---|---|
| G1 FIXTURE_UNCONFIRMED | No listed source confirms the fixture |
| G2 EARLY_SEASON | Either team has played fewer than 10 matches this season, across all competitions |
| G3 MANAGER_CHANGE | Either team changed manager in its last 6 matches |
| G4 ROTATION_RISK | Either team played in the previous 3 days, or has a European match in the next 3 days |
| G5 ABSENCES | A listed source shows 3 or more first-team players out or doubtful for either team |
| G6 NAME_UNMAPPED | A team is not in your canonical team-name list |

### Screener output (JSON file, same fields every day)

- schema_version, run_date_utc, notes (data gaps or blocked sources, else null)
- matches[]: match_id, competition (code), home, away (canonical names), kickoff_utc, lineup_status (none, expected or confirmed), absences_home, absences_away, rest_days_home, rest_days_away, source_urls
- excluded[]: match and reason code
- Every fact carries a source URL. A fact not found in a listed source is null. Claude never fills gaps from memory.

### Functional

- The bot accepts a .json document uploaded from your chat, downloads it through the Telegram Bot API and validates it against schema version 1 before computing anything.
- Per match, the bot returns P(home), P(draw), P(away) and P(over) for each line 0.5, 1.5, 2.5, 3.5, 4.5 and 5.5. Under is 1 minus over.
- The bot omits matches that fail the drift check and says why. **[v2]** It also omits a match with no stored forecast (`NO_FORECAST`) and says so; it never computes a number itself.
- Before each batch, the three models are refit and re-scored, and the ensemble is rebuilt.
- Every prediction is stored with its inputs and model version, and its result is added once the match finishes.
- The bot answers only your Telegram chat ID and ignores everyone else.
- **[Rev-1]** If an upload is accepted but never answered (for example the Worker is stopped by its CPU limit), you are alerted within about 6 hours.
- **[Rev-1]** A prediction whose match never shows as finished (for example a match moved to another day) is closed as void 3 days after kickoff and listed in an alert.
- **[v3]** The bot answers these commands, from your chat only. Every command only reads what is stored:

| Command | Shows |
|---|---|
| `/help` (also `/start`) | The list of commands |
| `/status` | The live model run and its age (stale or not), the data cut-off, which models fitted and their weights, the last result of each nightly step, the forecasts stored for today and tomorrow, uploads that were never answered, alerts waiting to be sent |
| `/fixtures [date]` | The fixtures with a stored forecast for the date (today to today + 4) and each one's verdict (ok, DRIFT, INSUFFICIENT_HISTORY, NO_MODEL), plus how many scheduled fixtures have no forecast. **No probabilities** |
| `/logged [date]` | The predictions already logged for the date, in the same layout as the upload reply |
| `/results [n]` | The latest settled predictions (default 10, at most 20): the score, the logged 1X2 numbers and the RPS, and voided ones with their reason |
| `/pending` | Logged predictions still waiting for a result |
| `/report` | The latest weekly report as text (progress toward 300 scored matches, RPS against the baseline with its interval, per model, omission rate) |
| `/last` | The outcome of the last upload (status, counts, error code) |
| `/team <name>` | A team's goals form (season against the last 10), matches in the data, and the verdict of its next stored fixture |
| `/alerts` | The alerts of the last 48 hours and whether each was delivered |

- **[v3]** `/fixtures` never shows a probability. Probabilities are shown only for the matches of an uploaded file, and again by `/logged` and `/results` once they are logged.
- **[v3]** No command logs a prediction, starts or stops a job, switches a model run or changes a stored prediction. Commands that would are not built.
- **[v3]** An unknown command gets "Unknown command. Send /help to see the commands." Any other text gets the usage hint, which now has a second line pointing to `/help`.
- **[v3]** Dates in commands are UTC calendar dates (`today`, `tomorrow`, `yesterday` or `YYYY-MM-DD`), the same dates the screener file uses; kickoff times are shown in UTC and IST as in the upload reply.

### Data

- Pipeline source: football-data.org free tier. It has 12 competitions, 10 requests per minute, delayed scores, no xG, no odds and no player stats. It supplies fixtures and results for nine of your competitions.
- Pipeline source: football-data.co.uk free CSV files (history for the leagues, and the Scottish Premiership). **[Rev-2]** You download them by hand and load them; they are never fetched automatically. If its terms do not allow that, this source and the Scottish Premiership are dropped. Its odds are collected on Friday afternoons for weekend games and Tuesday afternoons for midweek games, so they are not closing odds.
- Project sources: the official league and UEFA pages and the soccernews.com injuries pages listed in the appendix. The Project reads pages normally and never bulk-scrapes.
- Training history is the last 3 seasons with time decay.
- Team names map to the canonical list in the appendix. The bot keeps its own alias table for each source's spelling.
- **[Rev-1]** Clubs that played in these competitions during the 3-year window but are not in the 2026–27 lists are kept in a separate history-only (inactive) club list, so their past matches still count. A club in neither list is reported, never guessed.
- Not used: Transfermarkt. I could not verify that its terms allow automated reading, so it is left out.

### Non-functional

- Cost is $0. Free-tier limits can change, so verify them at build time.
- The bot runs as a Cloudflare Worker. Heavy model fitting runs outside the Worker, in the scheduled GitHub Actions job. **[v2]** So does all probability arithmetic; the Worker only validates, looks up, logs and renders.
- **[Rev-2]** Reply within 30 seconds of upload (p95).
- **[v3]** Reply to a command within 10 seconds (p95). A command must cost less Worker CPU than an upload.
- The bot token and API keys live in secrets, never in code. Keep source data out of any public repository; the repo is private.
- Judge accuracy by calibration, Ranked Probability Score, log loss and walk-forward backtesting. No closing odds are available free, so beating the market can't be measured.

## 8. Security, testing and deployment

The design keeps one trusted user, least-privilege tokens and no public data.

### Security

- Only your Telegram chat ID is answered; every other chat is ignored.
- The webhook is registered with Telegram's secret-token option, and the Worker rejects requests that lack the matching header.
- Bot token, football-data.org key and Cloudflare API token live in Worker secrets and GitHub Actions secrets, never in code.
- **[Rev-2]** Two Cloudflare tokens: the nightly job's is scoped to D1 only; the deploy token is used only by the deploy workflow.
- The repo is private, and source data stays out of any public repository.
- Uploaded files are validated with Zod before any computation. Anything that is not a valid schema-version-1 .json document is rejected.
- **[v3]** Commands pass the same three checks as uploads; anyone else still gets no reply at all. Text typed after a command (a date, a number, a team name) is length-capped and checked, and is never repeated back. No new secret or token is added to the bot.

### Testing

- Bot: Vitest with the Workers test pool. Zod fixtures for valid, malformed and wrong-version files.
- Models: pytest. Every scoreline grid must sum to 1, and 1X2 and over/under values must all come from the same grid.
- Walk-forward backtest on historical seasons, kept as a regression check for the Ranked Probability Score and calibration.
- Alias-table test: every canonical team name in the appendix resolves from each source's spelling.
- **[Rev-1]** One test runs the whole nightly job (fetch, score, fit, publish) on made-up data against a pretend database.
- **[v3]** Every command has tests, including one that proves a command writes nothing to the prediction log, and one that proves `/fixtures` never prints a probability. The upload tests stay unchanged and must stay green.

### Deployment

- Wrangler deploys the Worker from GitHub Actions.
- A scheduled workflow at 01:17 UTC (06:47 IST) ingests finished results, refits and re-scores the models, and writes parameters to D1.
- A final step sends a Telegram alert if the job fails.
- Reply fast: the Worker acknowledges the upload immediately and does its work after the acknowledgement. **[v2]** The reason is Telegram's retry behaviour, not CPU: background work does not lift the free plan's CPU limit, which is why the model arithmetic moved to the nightly job.

## 9. Legal

The legal risks are unchanged from the first draft and still open. This section is not legal advice.

- **Source terms unread.** Nobody has read the terms of football-data.org, football-data.co.uk, the official league sites or soccernews.com. Read each source's terms in build step 1 and drop or replace any source whose terms forbid it. **[Rev-2]** football-data.co.uk is never accessed automatically; you download its files by hand, and only if its terms allow that for personal use.
- **Gambling law.** Personal use only, probabilities only, no tips, given India's Public Gambling Act. Get legal advice before anyone else uses the system.
- **Data handling.** Keep source data out of public repositories. The repo is private, and that is a requirement, not a preference.
- **Transfermarkt.** Not used, because its terms could not be verified as allowing automated reading.

## 10. Edge cases and resolved decisions

Every case has a handling rule, and no decision is left open. "Default" rows are my picks, which you asked me to fill in. The two upload rows are new.

### Edge cases

| Situation | Handling | Status |
|---|---|---|
| Team missing from the canonical name list | Match excluded as G6 | Decided |
| Source page blocked or unreadable | Fact set to null and noted in notes; no workaround | Decided |
| No listed source confirms the fixture | Match excluded as G1 | Decided |
| A team has under 10 matches this season | Excluded as G2 by the screener; the models still train on prior seasons | Decided |
| Uploaded file is not .json, is malformed, or has the wrong schema version (Changed) | The bot rejects it, replies with the error and computes nothing | Default |
| Upload cannot be downloaded from Telegram (New) | The bot replies with an error and asks you to resend | Default |
| Message arrives from another Telegram chat | Ignored | Default |
| Match postponed or cancelled after you upload | Marked void in the log; no result is scored | Default |
| Match goes to extra time or penalties | Only 90 minutes plus stoppage time count for goals and 1X2 | Default |
| Newly promoted team with under 10 matches in the training data | Matches involving it are omitted, with the reason shown | Default |
| Data source rate limit hit or source down | Use cached data, retry at the next scheduled run and alert you | Default |
| One of the three models fails to fit | Run the other two and flag it in the reply | Default |
| Reply too long for one Telegram message | Split into several messages | Default |
| Upload accepted but never answered (**[Rev-1]**) | Alert to you within about 6 hours | Default |
| Match moved to another day or never reported as finished (**[Rev-1]**) | Prediction closed as void (no result) 3 days after kickoff and listed in an alert | Default |
| Champions League final at a neutral ground (**[Rev-1]**) | Treated like any match; the reply note says the final may be neutral | Default |
| A match in the file has no stored forecast (**[v2]**) | Omitted with reason `NO_FORECAST`; listed in the reply; nothing is computed in the bot | Decided |
| The latest stored forecasts are older than 36 hours (**[v2]**) | The reply carries the STALE MODELS banner | Default |
| Unknown command (**[v3]**) | "Unknown command. Send /help to see the commands." | Default |
| A command from another Telegram chat (**[v3]**) | Ignored, like any message | Decided |
| `/fixtures` for a date outside the forecast window (**[v3]**) | Says the window (today to today + 4, UTC dates) | Default |
| `/team` with a name not in our table, or several matches (**[v3]**) | Says no such team (the typed text is not repeated) or lists up to 5 of our canonical names | Default |
| No active model run when a command needs one (**[v3]**) | Says so; the watchdog alert covers the cause | Default |
| No weekly report stored yet (**[v3]**) | `/report` says so | Default |
| Command reply longer than one Telegram message (**[v3]**) | Split like upload replies | Default |
| A command fails unexpectedly (**[v3]**) | "Internal error, id=…" and an event; nothing is changed | Default |

### Resolved decisions

| # | Decision | Resolution |
|---|---|---|
| 1 | BTTS and correct score | Excluded from v1 |
| 2 | Morning run time | 08:00 IST, after the 06:47 IST fitting job |
| 3 | Claude's plain-language reading | Dropped from v1 |
| 4 | Failure alerts | Yes, a Telegram message to you |
| 5 | Success metric | Beat a league-average-frequency baseline on Ranked Probability Score over at least 300 logged matches |
| 6 | Ensemble weighting and model failure | Rolling Ranked Probability Score weights; if a model fails, run the rest and flag it |
| 7 | Where and when fitting runs | Scheduled GitHub Actions job at 01:17 UTC |
| 8 | Goal count with extra time or penalties | 90 minutes plus stoppage time only |
| 9 | Postponed or cancelled matches | Marked void in the log |
| 10 | Newly promoted teams | Omit matches when a team has under 10 matches of training data |
| 11 | Source rate limit or outage | Cached data, retry next run, alert you |
| 12 | Malformed input file | Reject with the error, compute nothing |
| 13 | Telegram access | Only your chat ID is answered |
| 14 | Reply longer than one Telegram message | Split into several messages |
| 15 | Source links and canonical team names | Filled in the appendix |
| 16 | JSON hand-off (New) | File upload only; no pasted JSON, because of Telegram's 4,096-character message limit |
| 17 | Tech stack and languages (New) | As in section 3; Python plus TypeScript; private GitHub repo |
| 18 | Drift inputs (**[Rev-1]**) | Goals only in v1; shots added later |
| 19 | Clubs that left the competitions (**[Rev-1]**) | Kept as history-only clubs so past matches count |
| 20 | Upload accepted but never answered (**[Rev-1]**) | Alert within about 6 hours |
| 21 | Match never reported as finished (**[Rev-1]**) | Void with reason no-result 3 days after kickoff |
| 22 | When to read source terms (**[Rev-1]**) | During build step 1, before any ingestion code |
| 23 | Switching on a new model run (**[Rev-1]**) | Safety checks only (models fitted, numbers sane, no team strength jump); no accuracy comparison until real results exist |
| 24 | History and Scottish Premiership source (**[Rev-2]**) | Hand-downloaded football-data.co.uk files if its terms allow; otherwise football-data.org only and the Scottish Premiership is dropped |
| 25 | Cloudflare tokens (**[Rev-2]**) | Two: nightly job D1-only, deploy token separate |
| 26 | Reply time (**[Rev-2]**) | Within 30 seconds of upload, p95 |
| 27 | Where probabilities are computed (**[v2]**) | In the nightly job, stored per fixture; the bot looks them up (replaces "bot computes") |
| 28 | Fixture with no stored forecast (**[v2]**) | Omitted as `NO_FORECAST`; no computation in the bot |
| 29 | Scottish Premiership (**[v2]**) | Not predicted in v1 (source decision A-1 path 2); matches omitted as insufficient history |
| 30 | Bot commands (**[v3]**) | Ten read-only commands from your chat: `/help` (`/start`), `/status`, `/fixtures`, `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team`, `/alerts` |
| 31 | Probabilities in `/fixtures` (**[v3]**) | Verdicts only; probabilities only for an uploaded file, so the screener's gates always apply and every number shown is logged |
| 32 | Commands that change things (**[v3]**) | Not built (no re-run, rollback, publish or void from chat; no GitHub or Cloudflare token in the bot); use the GitHub Actions tab |
| 33 | Commands and the prediction log (**[v3]**) | Commands never log or change a prediction; only an upload logs |
| 34 | Dates in commands (**[v3]**) | UTC calendar dates, as in the screener file; times shown in UTC and IST |

## 11. Verify at build and build order

None of these items change the stack, but each is a fact I recalled or could not confirm, so check it before relying on it.

### Verify-at-build checklist

- [ ] Read the terms of football-data.org, football-data.co.uk, the official league sites and soccernews.com (legal, section 9). **[Rev-1]** Do this during build step 1, as notes, before any ingestion code
- [ ] **[Rev-1]** How many past seasons football-data.org's free tier returns. If only the current season, most teams stay under 10 matches for weeks, and you decide the fallback then
- [x] Cloudflare Worker free-plan CPU limit per request (about 10 ms; **[v2]** measured on the real Worker: the planned design missed the 6 ms target, hence decision 27)
- [ ] Telegram Bot API file-download size cap (I recall 20 MB)
- [ ] Whether penaltyblog covers Dixon-Coles, bivariate Poisson and Ranked Probability Score; if not, implement them
- [ ] GitHub Actions free minutes for private repos (I recall 2,000 per month)
- [ ] Cloudflare D1 free-tier limits, and that Actions can write to D1 through Cloudflare's API
- [ ] grammY's Cloudflare Workers webhook adapter works with the current Workers runtime
- [ ] football-data.org free tier still matches the PRD (nine competitions, 10 requests per minute, no xG or odds)
- [ ] Each league's soccernews.com injuries page exists and shows an update date
- [ ] **[v3]** Telegram's `setMyCommands` with a chat scope shows the "/" menu in your private chat only

### Build order

1. Repo layout, secrets, the first D1 tables and the source-terms check **[Rev-1]** (each later step adds the tables it needs)
2. Data ingestion and the team-name alias table
3. Dixon-Coles with a walk-forward backtest, then the other two models and the ensemble
4. **[v2]** Nightly forecasts (the probabilities stored per fixture), then the bot: file upload, Zod validation, chat-ID allowlist, forecast lookup, reply splitting
5. Prediction log, Ranked Probability Score and calibration reporting (scoring, rolling weights, weekly report)
6. Failure alerts
7. **[v3]** Read-only bot commands (Essentials 3, Stage 8)

## 12. Appendix: sources and team names

Carried over unchanged. Team lists are the 2026–27 clubs as of 15 October 2026, taken from Wikipedia season pages and one NBC article (Premier League). The league and UEFA sites below are named as sources on those Wikipedia pages. I did not open them, so their terms and layout are unchecked.

### Fixture and result sources (Claude Project)

| Code | Competition | Primary page |
|---|---|---|
| EPL | Premier League | https://www.premierleague.com/ (not seen cited; unverified) |
| LL | La Liga | https://www.laliga.com/en-GB/laliga-easports/standing |
| BL | Bundesliga | https://www.bundesliga.com/en/bundesliga |
| SA | Serie A | https://www.legaseriea.it/en |
| L1 | Ligue 1 | https://www.ligue1.com/ranking |
| ERE | Eredivisie | https://eredivisie.com/competition/table/ |
| PPL | Primeira Liga | https://ligaportugal.pt/ |
| CHA | Championship | https://www.efl.com/competitions/efl-championship |
| SPL | Scottish Premiership | https://spfl.co.uk/league/premiership/table |
| UCL | Champions League | https://www.uefa.com/uefachampionsleague/standings/ |

Cross-check pages exist at soccernews.com for the Bundesliga, Serie A, Eredivisie and Primeira Liga, for example https://www.soccernews.com/soccer-stats/serie-a/fixtures-and-results/2026-27/.

### Injury and suspension source

Use the soccernews.com injuries-suspensions page for the competition. I confirmed these pages exist for the Premier League and the Primeira Liga; for the other leagues, check that the page exists. If a page is missing or shows no update date within the last 7 days, set absences to null. Transfermarkt is not used.

### Canonical team names

The bot keeps an alias table for each source's spelling (for example Hearts for Heart of Midlothian). Update the lists each summer for promotion, relegation and the Champions League draw. **[Rev-1]** A second list, history-only clubs (inactive), covers clubs that played in these competitions in the last 3 seasons but are not in the 2026–27 lists below; it is created during the build.

| Competition | Teams |
|---|---|
| EPL (20) | Arsenal, Aston Villa, Bournemouth, Brentford, Brighton, Chelsea, Coventry City, Crystal Palace, Everton, Fulham, Hull City, Ipswich Town, Leeds United, Liverpool, Manchester City, Manchester United, Newcastle, Nottingham Forest, Sunderland, Tottenham Hotspur |
| LL (20) | Alavés, Athletic Bilbao, Atlético Madrid, Barcelona, Celta Vigo, Deportivo A Coruña, Elche, Espanyol, Getafe, Levante, Málaga, Osasuna, Racing Santander, Rayo Vallecano, Real Betis, Real Madrid, Real Sociedad, Sevilla, Valencia, Villarreal |
| BL (18) | Augsburg, Bayer Leverkusen, Bayern Munich, Borussia Dortmund, Borussia Mönchengladbach, Eintracht Frankfurt, Elversberg, Freiburg, Hamburg, Hoffenheim, Köln, Mainz, Paderborn, RB Leipzig, Schalke, Stuttgart, Union Berlin, Werder Bremen |
| SA (20) | Atalanta, Bologna, Cagliari, Como, Fiorentina, Frosinone, Genoa, AC Milan, Inter Milan, Juventus, Lazio, Lecce, Monza, Napoli, Parma, Roma, Sassuolo, Torino, Udinese, Venezia |
| L1 (18) | Angers, Auxerre, Brest, Le Havre, Le Mans, Lens, Lille, Lorient, Lyon, Marseille, Monaco, Nice, Paris FC, Paris Saint-Germain, Rennes, Strasbourg, Toulouse, Troyes |
| ERE (18) | ADO Den Haag, Ajax, AZ, Cambuur, Excelsior, Feyenoord, Fortuna Sittard, Go Ahead Eagles, Groningen, Heerenveen, NEC, PEC Zwolle, PSV Eindhoven, Sparta Rotterdam, Telstar, Twente, Utrecht, Willem II |
| PPL (18) | Académico de Viseu, Alverca, Arouca, Benfica, Braga, Casa Pia, Estoril Praia, Estrela da Amadora, Famalicão, Gil Vicente, Marítimo, Moreirense, Nacional, Porto, Rio Ave, Santa Clara, Sporting CP, Vitória de Guimarães |
| CHA (24) | Birmingham City, Blackburn Rovers, Bolton Wanderers, Bristol City, Burnley, Cardiff City, Charlton Athletic, Derby County, Lincoln City, Middlesbrough, Millwall, Norwich City, Portsmouth, Preston North End, Queens Park Rangers, Sheffield United, Southampton, Stoke City, Swansea City, Watford, West Bromwich Albion, West Ham United, Wolverhampton Wanderers, Wrexham |
| SPL (12) | Aberdeen, Celtic, Dundee, Dundee United, Falkirk, Heart of Midlothian, Hibernian, Kilmarnock, Motherwell, Rangers, St Johnstone, St Mirren |
| UCL only (11) | AEK Athens, Bodø/Glimt, Club Brugge, Fenerbahçe, Galatasaray, LASK, Sabah, Shakhtar Donetsk, Slavia Prague, Slovan Bratislava, Viking |
