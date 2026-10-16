# Stage 1 setup (one time, needs Divine)

Everything below touches your Cloudflare and GitHub accounts, so Claude Code did not do it. Do it in this order. Never paste a token into the repo, a PR or a chat.

## A. Local development

```bash
npm ci                                  # JS dependencies from the lockfile
npm run hooks:install                   # pre-push hook that refuses pushes to main
cd apps/fit
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe --require-hashes -r requirements-dev.txt   # Windows
python -m pytest                        # run from apps/fit with that venv
```

Checks you can run any time: `npm run lint`, `npm run typecheck`, `npm test`, `npm run check:repo`, and in `apps/fit`: `ruff check .`, `ruff format --check .`, `mypy`, `pytest`.

## B. Already done by Claude Code (2026-10-16)

- D1 database `prob-bot` created in your Cloudflare account. Id `f0d80197-890a-4009-8844-4d0fc82223f4`, now in `apps/bot/wrangler.toml`. Account id `d0a180c20666ef79ae23567c024d1a21`.
- Your Workers subdomain is `gimafolabit`, so the Worker address will be `https://prob-bot.gimafolabit.workers.dev`.
- Migration `0001` is **not applied yet**: the permission check on the Cloudflare connection blocked writing the schema to the production database, and the connection cannot create API tokens (Cloudflare error 9109). You do not need to apply the migration by hand, because `deploy.yml` applies it on the first merge.

## C. What only you can do, in order

Everything here uses your own accounts. Never paste a token or secret into the repo, a pull request or a chat.

### C1. Make two random secrets (2 minutes)
In a terminal run this twice and keep the two outputs in a password manager:

```
node -e "console.log(require('crypto').randomBytes(24).toString('hex'))"
```

- First output = **path secret** (`WEBHOOK_PATH_SECRET`).
- Second output = **header secret** (`TELEGRAM_WEBHOOK_SECRET`). They must differ.

### C2. Create the Telegram bot
1. Open https://t.me/BotFather in Telegram, send `/newbot`, choose a name and a username ending in `bot`.
2. BotFather replies with the **bot token** (looks like `123456:ABC...`). Keep it in your password manager. If it ever leaks, send `/revoke` to BotFather.

### C3. Find your numeric Telegram id
Open https://t.me/userinfobot and send it any message. It replies with your numeric `Id`. Your private chat id is the same number. This is both `ALLOWED_CHAT_ID` and `ALLOWED_USER_ID`.

### C4. Put the four secrets into the Worker
From the repo folder `apps/bot`:

```
npx wrangler login
npx wrangler secret put WEBHOOK_PATH_SECRET
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
npx wrangler secret put ALLOWED_CHAT_ID
npx wrangler secret put ALLOWED_USER_ID
```

`wrangler login` opens https://dash.cloudflare.com in your browser to approve access. Each `secret put` prompts for the value (paste it there). If wrangler asks "create a new Worker with that name?", answer yes: the Worker is called `prob-bot`. Docs: https://developers.cloudflare.com/workers/configuration/secrets/

### C5. Create the two Cloudflare API tokens
Go to https://dash.cloudflare.com/profile/api-tokens and choose **Create Token > Create Custom Token** (guide: https://developers.cloudflare.com/fundamentals/api/get-started/create-token/).

| Token | Name | Permissions | Account resources |
|---|---|---|---|
| Nightly (used from Stage 2) | `prob-bot-nightly-d1` | **Account > D1 > Edit** only | Include > your account |
| Deploy | `prob-bot-deploy` | **Account > Workers Scripts > Edit**, **Account > D1 > Edit**, **Account > Account Settings > Read** | Include > your account |

Copy each token when it is shown (it is displayed only once). If a later deploy fails with an authentication error, add **User > User Details > Read** to the deploy token.

### C6. Add the GitHub secrets
Open https://github.com/DivineGima/PROB_BOT/settings/secrets/actions and click **New repository secret** for each row.

| Secret name | Value |
|---|---|
| `CF_ACCOUNT_ID` | `d0a180c20666ef79ae23567c024d1a21` |
| `D1_DATABASE_ID` | `f0d80197-890a-4009-8844-4d0fc82223f4` |
| `WORKER_URL` | `https://prob-bot.gimafolabit.workers.dev` |
| `CF_DEPLOY_TOKEN` | the deploy token from C5 |
| `CF_D1_TOKEN` | the nightly token from C5 |
| `TELEGRAM_BOT_TOKEN` | the bot token from C2 |
| `WEBHOOK_PATH_SECRET` | the path secret from C1 (same value as in C4) |
| `TELEGRAM_WEBHOOK_SECRET` | the header secret from C1 (same value as in C4) |

(Claude Code may already have added `CF_ACCOUNT_ID`, `D1_DATABASE_ID` and `WORKER_URL`; check the list and add only what is missing.)

### C7. Review and merge the pull request
1. Open https://github.com/DivineGima/PROB_BOT/pulls and open the Stage 1 pull request.
2. Wait for the four CI checks (TypeScript, Python, Repo rules, Secret scan) to be green. If one is red, send the failing log to Claude Code.
3. Merge it. `deploy.yml` then runs on `main`: guard, migration `0001`, deploy, webhook registration, smoke. Watch it at https://github.com/DivineGima/PROB_BOT/actions
4. Check the first deploy: send any message to your bot in Telegram (it stays silent in Stage 1, which is correct), then confirm the smoke step is green.

### C8. CPU gate (done for Stage 1; repeat only to re-measure)
Stage 1 ran this and recorded the result in `docs/verification.md` section 2 (the gate failed; see the tracker). To re-measure later:
1. Ask Claude Code to open a short pull request that sets `SPIKE_ENABLED = "1"` in `apps/bot/wrangler.toml`; merge it and wait for the deploy.
2. In the repo folder, in one PowerShell window, set `WORKER_URL`, `WEBHOOK_PATH_SECRET` and `TELEGRAM_WEBHOOK_SECRET` as environment variables and run `node scripts/cpu-spike.mjs`. It must print `"http_statuses":{"200":40}`. Then remove the two secret variables from the window.
3. Tell Claude Code. It reads the CPU times from Workers Logs (kept 3 days on the Free plan) and records them. No recording window is needed.
4. Merge the pull request that sets `SPIKE_ENABLED` back to `"0"`.

### C9. Live D1 probe (verify-at-build item 3)
No shell or token needed: run the `data` workflow with the command `d1-probe` (see C11) and tell Claude Code. It reads the JSON from the run log and records it in `docs/verification.md` item 3.

### C10. Legal decisions (done)
`docs/legal/source_terms_register.md` is signed: football-data.org enabled, A-1 path 2 (football-data.org only, Scottish Premiership dropped, football-data.co.uk not used). The `FD_ORG_TOKEN` GitHub secret exists.

### C11. Run the data commands (Stage 2)
Everything runs in GitHub with the stored secrets; you paste nothing. Open https://github.com/DivineGima/PROB_BOT/actions/workflows/data.yml , click **Run workflow**, keep **Branch: main**, pick a command, click the green **Run workflow** button, then tell Claude Code. In this order:
1. `bootstrap-dry-run`: fetches 3 seasons from football-data.org and writes nothing. It shows how many past seasons the free plan allows and lists club names we do not know yet. About 4 minutes.
2. Claude Code fixes the alias file from that report (pull request, you merge).
3. `bootstrap`: seeds teams and aliases and loads the history into D1. About 4 minutes. Safe to run again.
4. `ingest`: the nightly job's data step (last 7 days and next 3). Safe to run again.
5. `d1-probe` (optional, any time): the live D1 check from C9.

### C12. Model runs (Stage 3 and 4)
Same page as C11, commands in this order (after `ingest` has run at least once):
1. `backtest`: walk-forward evaluation against the league-frequency baseline. Defaults are a 365-day test period and a 3 x 3 sweep for Dixon-Coles only (a few minutes). For the full comparison set `models` to `dc,pi,bp` and `half_lives` / `shrinks` to one value each (about 10 to 20 minutes). The readable report is in the job log.
2. `fit`: fits dc, pi and bp, weights the ensemble, snapshots `team_form` and writes a `building` run. A model that fails is stored as failed with its reason (exit code 4); the others still run.
3. `publish`: runs the promotion gate and, if it passes, makes the run active. A rejected run leaves the previous run active and writes an `alert` event.

Rollback to the previous good run (a shell with the D1 token): `python -m footy.cli publish --rollback R<id>`. Look up ids in `model_runs` (status `superseded`).

## D. Branch controls

GitHub Free has no branch protection for private repos. The compensating controls are the `pre-push` hook (run `npm run hooks:install` on every machine you push from), the `deploy.yml` merged-PR guard, and the rule that only `deploy.yml` sees `CF_DEPLOY_TOKEN`. Keep working on `feat/...` or `fix/...` branches and merge through pull requests.
