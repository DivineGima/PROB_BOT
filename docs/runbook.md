# Runbook (Stage 7)

For Divine. What runs by itself, what to do when something is wrong, and the go-live checklist.
Everything below uses pages you already know: GitHub Actions, the Cloudflare dashboard and Telegram.

## 1. What runs by itself

| What | When | Where | If it fails |
|---|---|---|---|
| `nightly` workflow: ingest, score, fit, publish, (Monday) report, health check, alert delivery | 01:17 UTC (06:47 IST) | https://github.com/DivineGima/PROB_BOT/actions/workflows/nightly.yml | A Telegram alert says it failed, with the run link |
| Worker watchdog | every 6 h (minute 07) | Cloudflare Worker cron | A Telegram alert: no run published, run too old, no forecasts, or an upload never answered |
| `backup` workflow: export of the database | Sundays 02:43 UTC | https://github.com/DivineGima/PROB_BOT/actions/workflows/backup.yml | Red run in Actions (no alert); download the file from the run's Artifacts |
| `backtest` workflow | 1st of the month 03:23 UTC | https://github.com/DivineGima/PROB_BOT/actions/workflows/backtest.yml | Red run means a model got worse (informational) |

The schedule of `nightly` does nothing until you set the repository variable **NIGHTLY_ENABLED** to `true`
(https://github.com/DivineGima/PROB_BOT/settings/variables/actions). Do that after one manual run has been green.

## 2. Daily ritual

1. Run your screener and send the `.json` file to the bot as a document.
2. Read the reply. `Omitted:` lists the matches that got no numbers and why.
3. Nothing else. Alerts arrive by themselves.

## 3. When an alert arrives

| Alert says | Meaning | What to do |
|---|---|---|
| The nightly job failed | A step went red | Open the link in the alert, read the red step. Re-run with **Run workflow** (nightly). If `ingest` failed on a source outage it carries on by itself |
| Model run ... was rejected | The new run failed its checks; the old run still serves | Read the reasons in the alert. If the large move is real, run `publish` from the data workflow with `run_id` and accept-drift only after thinking about it |
| Every model failed | No new run | Re-run `fit` then `publish` (data workflow). If it repeats, tell Claude |
| No model run is published / run is N h old | The bot may show STALE MODELS or nothing | Run nightly by hand. If the schedule never started, check NIGHTLY_ENABLED and https://github.com/DivineGima/PROB_BOT/actions |
| No forecasts are stored for a day | Every match would be `NO_FORECAST` | Run `ingest`, `fit`, `publish` from the data workflow |
| Upload(s) acknowledged but never answered | The Worker was cut off | Send the file again; it is safe (a repeat is reported as already logged) |
| Health check `bot_token` failed | In the last 24 h the Worker could not reply or alert: bot token missing or refused, unusable chat id, or a watchdog crash | Re-enter the token and check `ALLOWED_CHAT_ID` (section 5). The alert clears by itself 24 h after the cause is fixed |
| Unmapped team / team missing from the canonical list | A club name is unknown | Add an alias or the team (ask Claude); until then its matches are skipped |

## 4. Rollback

- **Model run:** data workflow, command `publish`, and use the rollback input in a future version; today ask Claude to run
  `footy publish --rollback <run id>` (the five newest runs keep their forecasts).
- **Worker code:** revert the pull request on GitHub; the deploy workflow redeploys the previous version.

## 5. Rotating a secret (drill once)

| Secret | Where | How |
|---|---|---|
| Bot token | BotFather (`/revoke`), Worker, GitHub | New token from https://t.me/BotFather, then `npx wrangler secret put TELEGRAM_BOT_TOKEN` (in `apps/bot`), update the GitHub secret `TELEGRAM_BOT_TOKEN`, re-run `deploy` so the webhook is registered |
| D1 token | Cloudflare dashboard | Create a new D1-only token, update GitHub secret `CF_D1_TOKEN`, delete the old one |
| Webhook secrets | Worker and GitHub | Change both `TELEGRAM_WEBHOOK_SECRET` and `WEBHOOK_PATH_SECRET` the same way, re-run `deploy` |

## 6. Restore drill (do once)

1. Download the latest `prob-bot-d1-export` artifact from the `backup` workflow run.
2. Create a scratch database: `npx wrangler d1 create prob-bot-restore-test`.
3. `npx wrangler d1 execute prob-bot-restore-test --remote --file prob-bot.sql`.
4. Check: `SELECT COUNT(*) FROM matches;` and `SELECT * FROM active_run;`.
5. Delete the scratch database. Never restore over the live one without asking Claude.

## 7. GitHub auto-disable

GitHub switches off scheduled workflows after 60 days without repository activity for **public** repositories; this one is private.
Check once at https://github.com/DivineGima/PROB_BOT/settings (visibility private) and note the date here: ______.
If the repository ever becomes public, the Worker watchdog still alerts when the nightly job stops publishing.

## 8. Go-live checklist

- [ ] Legal register signed for football-data.org (`docs/legal/source_terms_register.md`).
- [ ] CI green on `main`; deploy green.
- [ ] Secrets present: Worker `TELEGRAM_BOT_TOKEN`; GitHub `TELEGRAM_CHAT_ID`, `TELEGRAM_BOT_TOKEN`, `FD_ORG_TOKEN`, `CF_D1_TOKEN`, `CF_ACCOUNT_ID`, `D1_DATABASE_ID`.
- [ ] `nightly` run by hand (Run workflow) once, green end to end, and the Telegram alert path proven (see section 9).
- [ ] `backup` run by hand once, artifact downloaded and the restore drill done.
- [ ] Variable `NIGHTLY_ENABLED` set to `true`.
- [ ] Seven nightly runs in a row green (the date of the first: ______).
- [ ] A real screener upload answered, and the `score` and weekly `report` seen once.
- [ ] Decision recorded for the 16 test predictions in the live log (keep or delete).

## 9. Proving the alert path once

From the data workflow run `report`: it sends through the same Telegram sender as the alerts, so a message arriving proves the path.
The watchdog sends only when something is wrong; to see it once, ask Claude to trigger it with a test finding.
