# Tracker, version 3 (PRD_3, system_architecture_3, essential_3)

> Trackers follow the version number N (claude.md §5): tracker_1 = version 1, tracker_2 = version 2, tracker_3 = version 3, tracker_4 = version 4. Entries were split out of `tracker_1.md` on 2026-11-21 word for word; nothing was reworded.

## 2026-11-21 (version 3) - Read-only bot commands designed: PRD_3, architecture 3, essentials 3 (no code written)

- **Built against:** `PRD_3.md`, `system_architecture_3.md`, `system_architecture_essential_3.md` (all N=3), written this session. Branch `feat/v3-bot-commands-docs`. Documents only; no code, schema, workflow or secret changed.
- **Why a version 3 and not an edit of version 2:** architecture §1.4 and ADR-016 listed "bot commands beyond the upload flow" as out of scope, so adding them is a scope change. `claude.md` forbids editing an earlier version and requires PRD, architecture and essentials to share N. Version 2 already existed, so the new snapshot is 3. Divine asked for the documents in this session (an exception to "PRD and architecture changes are made in design chat", recorded in the revision lines of all three files, as essentials 2 did).
- **Read order and drift checks (claude.md section 1):** before writing, the current files were PRD_2, architecture 2 and essentials 2; essentials 2 named architecture 2, and architecture 2 was derived from PRD_2, so there was no drift. After writing: essentials 3 names `system_architecture_3.md` and `PRD_3.md`; architecture 3 says `Derived From: PRD_3.md`; the highest N in `/prd/`, `/system_architecture/` and `/essentials/` is 3 in all three. The changelogs of PRD_3 and architecture 3 both say `IMPACT`, and essentials 3 is the follow-up they name.
- **Decisions by Divine (2026-11-21):** all ten commands: `/help` (also `/start`), `/status`, `/fixtures`, `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team`, `/alerts`. `/fixtures` shows verdicts only, never probabilities (ADR-050). The state-changing commands (`/rerun`, `/rollback`, `/publish`, `/void`) were recommended against and are not built (ADR-051).
- **Design in short (architecture §6.10, §8.12):** a new Worker module `commands/` over a read-only `QueryRepository` (`SELECT` only); `/status` reuses the watchdog's `collectFindings`; no migration; no new secret (`deploy.yml` reads the existing `TELEGRAM_CHAT_ID` for the menu scope); Telegram menu by `setMyCommands`, scoped to the allowed chat (ADR-052); new invariant 9 (the command path writes only `processed_updates` and `command_failed`); threats S15 to S17; risks R-P13, R-O8, R-M9; ADR-049 to ADR-052. Two rules that exist in both languages (the alert predicate and the team-name normaliser) are pinned by a repository check and shared vectors.
- **Also changed:** `README.md` links the version-3 files and says the commands are planned, not built.
- **Checked against the code before writing:** the text-message branch in `apps/bot/src/index.ts` (where commands plug in); `processed_updates.kind` has no CHECK (a new value `command` needs no migration); `collectFindings` is pure over the repositories; watchdog findings are recorded as `error` events only after delivery (so `/alerts` lists them as "sent by watchdog"); the flush predicate in `OpsRepo.pending_alerts`; the `metrics_json` keys written by `report/metrics.py`; the job kinds in `job_runs`; only `fd_org` aliases exist in `data/aliases/`.

### Module status
| Module | Status |
|---|---|
| Stages 1 to 7 | **complete** (unchanged) |
| Version-3 documents (PRD_3, architecture 3, essentials 3) | **complete**, waiting for Divine's review and merge |
| Stage 8: read-only bot commands | not started (next, after the documents are merged) |

### Open issues
1. Divine reviews and merges the documents pull request; Stage 8 starts only after that.
2. Stage 8 step 9 needs Divine's phone and a second Telegram account (menu not shown, stranger gets no reply).
3. Carried over: Divine's GitHub billing check; PR #3 (TypeScript 7) waits for a Dependabot rebase; local `biome check` on Windows reports CRLF; the earlier open items (`claude.md` in-place-edit wording, missing design-rules file, git identity).

---

## 2026-11-21 (Stage 8) - Read-only bot commands built and live (steps 1 to 8 complete; step 9 waits for Divine)

- **Built against:** `PRD_3.md`, `system_architecture_3.md`, `system_architecture_essential_3.md` Stage 8 (all N=3). One branch and one pull request per step, each merged after green CI: #44 (step 1), #45 (2), #46 (3), #47 (4), #48 (5), #49 (6), #50 (7), and this docs PR (8).
- **Read order:** the tracker showed Stages 1 to 7 built. Their remaining items are Divine's live checks (the drills, the 16 test predictions) and block no code. Essentials 3 was the next file with work; drift checks as in the version-3 entry (N=3 everywhere, no drift).
- **What exists now:**
  - **Commands:** ten read-only commands answer in the allowed chat: `/help` (`/start`), `/status`, `/fixtures` (verdicts only), `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team`, `/alerts`.
  - **Menu:** Telegram's "/" menu is registered at every deploy, scoped to the chat.
  - **Usage hint:** it gains the line "Send /help to see the commands."
  - **Unchanged:** the upload pipeline, the schema (no migration), the Python job and the secrets (no new one; `deploy.yml` reads the existing `TELEGRAM_CHAT_ID`).
- **Safety, as tested:**
  - Every command through the real webhook leaves the full contents of 13 tables unchanged and writes no event (invariant 9).
  - A stranger, another user or a group gets no reply and causes no read.
  - A replay is answered once.
  - D1 failing mid-command gives `Internal error, id=...` and changes nothing.
  - `/fixtures` never prints a probability.
  - `repo/queries.ts` is checked read-only by `check-sql-locality.mjs`.
  - The alert lists and the team-name normaliser are pinned to the Python and watchdog sources by `scripts/cross-language.test.mjs` and the shared vectors `packages/contracts/golden/normalise.json`.
  - The `/report` keys are pinned by pytest.
- **Measured:**
  - **D1 calls per command:** `/status` 4, `/team` 2, the others 1, `/help` and bad input 0, with one Telegram send each.
  - **Production:** deploy `0ca6e66` (commands live) and `c10a749` (menu: `set-webhook: command menu ok`) both green.
- **Tests:** Worker 360 (was 238 at the start of the day), script tests 60, Python 648 (41 of them new contract tests). `tsc`, Biome, ruff, mypy and the repo checks are clean in CI.
- **As built:** recorded in architecture §20.1 (the `QueryRepository` method set, `/status` making 4 D1 calls instead of at most 2, `/logged` using its own query so the upload's query stays untouched, the `/team` matching order, where the read-only and cross-language checks live).
- **Docs:** `docs/runbook.md` section 10 (each command, and which command answers which alert); README "Bot commands"; `docs/verification.md` section 8.
- **Lesson for later sessions:** on this machine the shell collapses double backslashes inside heredocs, so text with backslashes is written through script files. Biome's formatter on Windows also turns `\u` escapes inside regexes into literal characters.

### Module status
| Module | Status |
|---|---|
| Stages 1 to 7 | **complete** (unchanged) |
| Stage 8 steps 1 to 8: grammar, read-only queries, cross-language pins, renderers, handlers and routing, menu, behaviour tests, docs | **complete** |
| Stage 8 step 9: production check with Divine's phone | **in-progress** |

### Open issues
1. **Step 9 (Divine):**
   - send each command once;
   - from a second Telegram account, confirm `/status` gets no reply and the menu is not shown;
   - Claude Code then reads `cpuTime` from Workers Logs (10+ requests each of `/status`, `/fixtures`, `/team`) and fills `docs/verification.md` section 8.

   Stage 8 becomes `complete` after that.
2. **Carried over:** Divine's GitHub billing check; PR #3 (TypeScript 7) is superseded by #42 (already on main) and can be closed; local `biome check` on Windows reports CRLF; the earlier open items (`claude.md` in-place-edit wording, missing design-rules file, git identity).

---

## 2026-11-21 (Stage 8 step 9) - Production check done by Divine; Stage 8 complete

- **Built against:** `system_architecture_essential_3.md` Stage 8 step 9, architecture 3.
- **What happened:** Divine reported on 2026-11-21 that he sent each command in the real chat and did the second-account check (no reply, no menu).
- **Not measured:** the `cpuTime` figures from Workers Logs. The Cloudflare login (`wrangler`) has expired and the Cloudflare connector is not authorised. Carried into Stage 9 step 6 (essentials 4), where the same log reading covers both stages. Recorded in `docs/verification.md` section 8.

### Module status
| Module | Status |
|---|---|
| Stages 1 to 8 | **complete** |

### Open issues
1. `cpuTime` of the commands: carried to essentials 4 Stage 9 step 6 (needs `wrangler login` once).
