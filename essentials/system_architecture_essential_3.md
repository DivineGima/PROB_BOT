# Essentials Phase 3 — Read-only bot commands — Football Reliability Screener and Probability Bot

## Aim & Outcome
Version 3 lets Divine ask the bot for what is already stored, from the private chat, with ten read-only commands: `/help` (also `/start`), `/status`, `/fixtures`, `/logged`, `/results`, `/pending`, `/report`, `/last`, `/team` and `/alerts` (architecture §6.10, ADR-049). `/fixtures` shows verdicts only, never probabilities (ADR-050). No command changes state (ADR-051). This file holds only the new work, as one new **Stage 8**. Stages 1 to 7 of `system_architecture_essential_1.md` and `system_architecture_essential_2.md` are unchanged and stay as built.

Success for this phase: every command answers correctly in the real chat. A stranger's command gets no reply. No command writes to the prediction log, the forecasts or the model runs. The existing upload flow behaves exactly as before. The product success metric is unchanged (PRD_3): beat the league-frequency baseline on RPS over at least 300 logged matches.

Source PRD: PRD_3.md

Source Architecture Version: system_architecture_3.md

Revision: first issue, 2026-11-21. Written by Claude Code at Divine's instruction ("create the PRD, the architecture, the essentials and the tracker" for the bot commands). The command list and the verdicts-only rule are Divine's decisions of 2026-11-21. Numbered 3 because PRD, architecture and essentials share N and version 2 already exists.

## Source Architecture Components
References only. Every step also obeys `## Extensibility & Change-Tolerance` and `claude.md`.

- §6.10 I-8 bot commands (grammar, dates, the command table, the alert definition, the `/report` read contract, limits)
- §6.2 update kinds; §6.3 behaviour matrix ([v3] rows); §6.4 `setMyCommands`; §6.5 `commands` module and `QueryRepository`; §6.6 error catalogue note
- §7.3 Worker components; §7.6 project structure; §7.12 command data flow; §8.12 deep dive
- §5.7 invariant 9 (the command path writes nothing that matters)
- §9.1 threats S15 to S17 and the secrets inventory (`TELEGRAM_CHAT_ID` in `deploy.yml`); §9.2 observability; §9.3 `deploy.yml`; §9.5 tests; §9.6 idempotency
- §15 risks R-P13, R-O8, R-M9; §16 [v3] verify-at-build items
- ADR-042, ADR-044, ADR-048 (constraints kept), ADR-049, ADR-050, ADR-051, ADR-052

## Build Steps
Work in step order. Open one pull request per step, never to `main` directly. A step's tests must be green before the next step starts. Write a `/tracker/` entry after each working session. No migration is needed. If one turns out to be needed, stop and flag it: it would be an architecture change.

### Stage 8 — Read-only bot commands

1. **Command list and grammar (pure):**
   - **Command list:** `packages/contracts/bot_commands.json` holds name, argument hint and one-line description for each command.
   - **Parser:** `apps/bot/src/commands/parse.ts` provides `parseCommand(text)`, implementing the §6.10 grammar:
     - first character `/`;
     - a `@<bot>` suffix is removed;
     - the token is lower-cased and must match `^/[a-z_]{1,32}$`;
     - arguments are cleaned and capped at 64 characters;
     - `/start` is an alias of `/help`.
   - **Argument parsers:** `today|tomorrow|yesterday|YYYY-MM-DD` as a UTC date with a calendar check, and an integer in a range.
   - **Tests:**
     - upper case, a `@bot` suffix, leading and trailing spaces;
     - over-long arguments, control and direction characters;
     - an unknown command, `/start`;
     - 2026-02-29 rejected and 2028-02-29 accepted;
     - a date in the `+1d` IST case.
   - **Registry check:** the registry equals the JSON file.
2. **Read-only repository (`apps/bot/src/repo`):**
   - **Methods:** `QueryRepository` with the methods named in §6.5, with bound parameters only and one batch per method. `SELECT` (or `WITH ... SELECT`) statements only.
   - **Alert kinds:** two constant lists, the flush kinds and the watchdog finding kinds, sit next to the alert query.
   - **Tests on local D1 with seeded rows:**
     - the active run summary never returns a payload;
     - `forecastVerdicts` reads the active run only and counts scheduled fixtures without a row;
     - `settled` and `pending` order and limits;
     - the alert predicate on every kind (alert level, the two warn kinds, `anomaly_*`, watchdog kinds, a non-alert event);
     - `teamCandidates` with an alias hit and with none;
     - `teamForm` without an active run.
   - **Repo checks:** the SQL-locality check stays green. A new repo check fails if a `QueryRepository` statement does not begin with `SELECT` or `WITH`.
3. **Cross-language pins (§8.12, R-O8):**
   - **Name normaliser:** `commands/normalise.ts` normalises exactly as `footy/aliases` does. Shared vectors live in `packages/contracts/golden/normalise.json` (accents, ligatures, punctuation, apostrophes, `Bodø/Glimt`, `Fenerbahçe`, `1. FC Köln`-style input, extra spaces). Vitest and pytest both read the vectors.
   - **Alert kinds:** a repo check compares the TypeScript flush-kind list with `_WARN_ALERT_KINDS` in `apps/fit/src/footy/repo/ops.py`, and the watchdog-kind list with the kinds `watchdog/index.ts` records.
   - **Report keys:** a pytest asserts that `compute_metrics` returns every key of the `/report` read contract (§6.10).
4. **Renderers (`apps/bot/src/format/commands.ts`, pure):**
   - **One renderer per command, laid out as §6.10 says.** They reuse `formatKickoff`, `renderMatch`, `clean`, `splitBlocks` and `packLines`. At most 5 messages; a longer list ends with "and N more".
   - **Text sources:** team names come from our table. Arguments are never interpolated.
   - **Tests:**
     - a snapshot per command (small and large inputs, empty states: no run, nothing logged, no report, no upload, no alerts);
     - **`/fixtures` output contains no `%` and no probability value**, also when the stored rows hold probabilities;
     - `/report` with keys missing shows `n/a`;
     - an injection string stored as an alert kind or a team name renders cleaned.
5. **Handlers and routing (`apps/bot/src/commands/index.ts`, `apps/bot/src/index.ts`, `telegram/update.ts`):**
   - **`handleCommand(deps, chatId, parsed)`** is called from `runPipeline` for a `message.text` that starts with `/`. Any other text still gets the usage hint, now with the second line "Send /help to see the commands."
   - **Update kind:** `classifyUpdate` returns `command` for such text (stored in `processed_updates.kind`). A document is unchanged.
   - **`/status`** calls the watchdog's `collectFindings` and does not copy its checks.
   - **Failure path:** an unexpected exception replies `E_INTERNAL` with an id and writes one `command_failed` event (hourly dedupe key).
   - **Missing bot token:** records `bot_token_missing`, as the usage hint does.
   - **Request log line:** carries the outcome and the known command name, never the arguments.
   - **The upload pipeline is not modified.**
6. **Telegram menu (ADR-052):**
   - **Registration:** `scripts/set-webhook.mjs` also calls `setMyCommands` with `scope: {type: "chat", chat_id}` and the list from `bot_commands.json`.
   - **Failure handling:** without a chat id, it skips with a warning. A failed `setMyCommands` is a warning (exit 0). A failed `setWebhook` stays fatal.
   - **Deploy:** `deploy.yml` passes the existing secret `TELEGRAM_CHAT_ID` to that step only.
   - **Tests in `scripts/tools.test.mjs`:** the request body and scope; skip without a chat id; warning on failure; webhook failure still fatal.
7. **Behaviour tests (Vitest, local D1, fake Telegram `fetch`):**
   - **Behaviour-matrix rows:** every [v3] row of §6.3.
   - **Read-only proof (invariant 9):** after each command, the row counts and contents of `predictions`, `omissions`, `uploads`, `fixture_forecasts`, `model_runs`, `active_run`, `team_form` and `calibration_snapshots` are unchanged.
   - **Auth and replay:**
     - a command from another chat, from another user in the allowed chat, or in a group gets no reply (S2, S16);
     - a replay of the same `update_id` gives no second reply.
   - **Failure injection:** D1 throws during a read; `sendMessage` fails; 429 with `retry_after`.
   - **Splitting:** 60 fixtures in `/fixtures`; 30+ pending predictions.
   - **Limits:** subrequest count of each command at most 7; injection strings in every argument.
   - **Regression:** the full existing Worker suite unchanged and green.
8. **Docs:**
   - `docs/runbook.md` gains a "Commands" section: what each shows, and which command answers which alert ("stale run": `/status`; "stuck upload": `/last`; "no forecasts": `/fixtures`).
   - `README.md` lists the commands and links the version-3 files.
   - Differences found while building go into an as-built table in architecture §20 (a new subsection §20.1, added in place like §19.1).
9. **Production check (needs Divine's chat; Claude Code records it):**
   - **Deploy:** after merge, `deploy.yml` is green and its log shows the menu registered.
   - **Each command once in the real chat.** Compare `/status` with the watchdog and the last nightly, `/fixtures` with an upload of the same day, and `/logged` with that upload's reply.
   - **From another Telegram account:** `/status` gets no reply and the menu is not shown.
   - **CPU:** from Workers Logs `cpuTime`, at least 10 requests each of `/status`, `/fixtures` and `/team`, plus the first request after a quiet spell. Also reply time (target p95 ≤ 10 s, NFR-12). Recorded in a new section of `docs/verification.md`.
   - **If a command repeatedly exceeds 10 ms:** apply the F1 trims of §8.12 and escalate to Divine. The paid plan is an architecture change.
10. **Exit criteria:**
    - steps 1 to 8 merged with CI green;
    - the production check of step 9 recorded;
    - nothing written by any command except `processed_updates` and `command_failed`;
    - a `/tracker/` entry marking Stage 8 `complete`.

    Step 9 needs production and Divine's phone, so Stage 8 stays `in-progress` until it is done.

## Added test requirements
| Test | Step |
|---|---|
| Grammar: case, `@bot` suffix, 64-character cap, control characters, `/start` alias, unknown command | 1 |
| Command registry equals `packages/contracts/bot_commands.json` | 1 |
| `QueryRepository` statements are `SELECT`/`WITH` only (repo check) | 2 |
| Alert predicate on every event kind; TypeScript kind lists equal the Python list and the watchdog's | 2, 3 |
| Normaliser vectors equal in TypeScript and Python | 3 |
| `compute_metrics` keeps the `/report` read-contract keys | 3 |
| `/fixtures` never prints a percentage or a probability | 4 |
| No command changes any logged, forecast, run, form or snapshot row (invariant 9) | 7 |
| A command from a stranger gets no reply; a replayed command no second reply | 7 |
| `/status` and the watchdog report the same findings on the same data | 5, 7 |
| `setMyCommands` scoped to the chat; a menu failure does not fail the deploy | 6 |
| Existing upload, watchdog and intake tests unchanged and green | 7 |
