# Essentials Phase 4 — Visual messages and the strongest call — Football Reliability Screener and Probability Bot

## Aim & Outcome
Version 4 makes every Telegram message easy to read on a phone (emoji bars, icons, labels; ADR-053), adds the strongest call per match (ADR-057), a daily results picture (ADR-054) and a plain-language weekly report with a four-panel chart (ADR-055), all drawn from one display contract (ADR-056). This file holds only the new work, as one new **Stage 9**. Stages 1 to 8 stay as built.

Success for this phase: the mockups Divine approved on 2026-11-21 are what he sees in the real chat; `/fixtures` still shows no probability; nothing logged changes; the Worker stays inside its CPU budget. The product success metric is unchanged (PRD_4).

Source PRD: PRD_4.md

Source Architecture Version: system_architecture_4.md

Revision: first issue, 2026-11-21. Written by Claude Code at Divine's instruction. **One combined pull request** for the whole stage, at Divine's request (2026-11-21), instead of one per step; every other rule of claude.md applies (feature branch, CI green, no push to `main`).

## Source Architecture Components
- Changelog version 4 and §21; ADR-053 to ADR-057
- §3.4 budgets; §6.4 outbound; §6.5 `QueryRepository.settled`; §6.7 CLI `digest`; §6.10 commands and the `/report` read contract
- §7.9 nightly order; §8.1, §8.7, §8.8, §8.12; §9.3 nightly.yml; §9.5 tests; §9.6 idempotency
- §15 risks R-V1 to R-V4

## Build Steps

### Stage 9 — Visual messages and the strongest call

1. **Display contract and strongest call:** `packages/contracts/display.json`, `packages/contracts/golden/strongest.json`, `apps/bot/src/format/display.ts`, `apps/fit/src/footy/report/display.py`. Tests: the vectors in Vitest (`display.test.ts`) and pytest (`test_display_digest.py`).
2. **Upload reply:** `renderMatch`, `renderOmission`, the footer in `apps/bot/src/format/index.ts`. Tests: the exact card, labels, a result as strongest call, 10 cells per bar, 100 matches split whole under 3,900 characters and within the subrequest budget. The upload pipeline's logic is unchanged.
3. **Commands:** `apps/bot/src/format/commands.ts` (all ten), `QueryRepository.settled` reads the over lines. Tests: `commands-format.test.ts`, `commands.test.ts`, `commands-webhook.test.ts` (invariant 9 and "no % in /fixtures" kept).
4. **Weekly report:** additive keys in `metrics.py`, `text.py`, `chart.py` (four panels), `/report` renderer. Tests: `test_report.py`, `test_display_digest.py`, the read-contract pin.
5. **Daily digest:** `footy/report/digest.py`, `PredictionsRepo.scored_after`, `cli.py digest`, the nightly step after Publish with the Telegram secrets only. Tests: two pictures for 14 matches, nothing new means no send, first run 48 h, a failed send is retried; `test_workflows.py` (order and secrets).
6. **Production check (needs Divine's phone and `wrangler login`):** deploy; one real upload; each command once; the next morning's picture; the Monday report; `cpuTime` p95 of an upload and of `/status`, `/fixtures`, `/results` (also Stage 8's carried figures) into `docs/verification.md` section 9. If p95 > 6 ms: F1 trims, then escalate.
7. **Docs:** README, runbook, as-built §21.1, `tracker_4.md`.

## Exit criteria
- the combined PR merged with CI green;
- step 6 recorded;
- a `tracker_4.md` entry marking Stage 9 `complete`.
