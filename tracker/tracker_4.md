# Tracker, version 4 (PRD_4, system_architecture_4, essential_4)

> Trackers follow the version number N (claude.md §5). Earlier entries: `tracker_1.md` to `tracker_3.md`.

---

## 2026-11-21 (version 4) - Visual Telegram messages and the strongest call: designed and built in one combined PR

- **Built against:** `PRD_4.md`, `system_architecture_4.md`, `system_architecture_essential_4.md` Stage 9 (all N=4).
- **Read order:** essentials 3 is complete (Stage 8 step 9 done by Divine, see tracker_3). Drift checks: essentials 4 names architecture 4; architecture 4 is derived from PRD_4. N=4 everywhere.
- **Why:** Divine found the plain-text replies hard to read. He approved the mockups on his phone (7 pictures, 2026-11-21) and chose: bars + images for every message, and a "strongest call" per match from 1X2 plus over/under 1.5 to 3.5.
- **One combined PR:** Divine asked for all of Stage 9 in one pull request instead of one per step (2026-11-21). Recorded in essentials 4.
- **Findings of the day (before the build):**
  - accuracy over the 48 graded predictions: favourite right 22 of 48 (46%) against the benchmark's 18; ensemble RPS 0.2163 against 0.2373; 95% interval -0.0515 to +0.0084 (includes zero);
  - the strongest-call rule would have been right 42 of 48 (88%) against a stated 81%;
  - no upload since 2026-10-25, so nothing new has been graded since; 12 predictions of 2026-10-24 were voided `NO_RESULT`;
  - the Cloudflare login (`wrangler`) has expired.
- **What exists now:**
  - `packages/contracts/display.json` (bars, labels, icons, grades, strongest-call candidates) and `packages/contracts/golden/strongest.json` (50 vectors), read by `apps/bot/src/format/display.ts` and `apps/fit/src/footy/report/display.py`;
  - the upload reply as a visual card (bars, most likely result with label, strongest call, goal lines);
  - all ten commands restyled; `/results` and `/logged` show whether the favourite and the strongest call came true; `/report` shows the new plain figures; `/fixtures` still shows no probability;
  - `metrics.py` gains additive keys `strongest`, `favourite`, `outcomes`, `overs`, `goals`; the weekly text and the 4-panel chart are rewritten;
  - `footy digest --send`: the daily results picture, a nightly step after Publish; high-water mark `through` in `job_runs.summary_json`; first run looks back 48 h.
- **Unchanged:** models, data, the upload pipeline's logic, the database schema (no migration), secrets (the digest step uses the existing Telegram secrets).
- **Tests:** Worker 420 (was 360), Python 704 locally (with the new `test_display_digest.py`), ruff clean. mypy and the hash-checked install run in CI.

### Module status
| Module | Status |
|---|---|
| Stage 9 steps 1 to 5 and 7: display contract, upload reply, commands, weekly report, daily digest, docs | **complete** (in the combined PR) |
| Stage 9 step 6: production check and `cpuTime` | **in-progress** (after merge; needs one real upload and `wrangler login`) |

### Open issues
1. Step 6: deploy, one real upload, each command once, the next morning's picture and the Monday report on Divine's phone; then `cpuTime` (also for Stage 8) into `docs/verification.md` section 9.
2. Upload the screener file daily again: progress to 300 graded predictions is stalled at 48.
3. Carried over: GitHub billing check; PR #3 can be closed; Biome on Windows reports CRLF; the GitHub MCP token has expired.
