# claude.md — Coding-agent guardrail (Football Reliability Screener and Probability Bot)

This file is edited in place (not versioned). Read it fully at the start of every coding task. Where it conflicts with convenience, this file wins. Where a source document conflicts with it, **halt and flag**.

## 1. Mandatory read order at the start of any coding task

Do these in order. A halt-and-flag at any step stops the whole sequence: do not continue to later steps and do not start coding.

1. **`/tracker/tracker_N.md`** (the highest N; one tracker per version, `tracker_N` matches PRD_N) — find the current phase and per-module status from the dated entries (Claude Code–maintained). Each entry must carry: a date, which essentials file + architecture version it was built against, and a status per module (`in-progress` / `complete`). If `/tracker/` is empty or has no entries (a `.gitkeep` alone), that is **not** an error: no phase has started — begin at `system_architecture_essential_1.md`.
2. **`/essentials/system_architecture_essential_N.md`** — the lowest-numbered essentials file that still has an incomplete stage per `/tracker/` (essential_1 if nothing has started). `essential_1` is the whole MVP, with every build step as ordered stages inside it; `essential_N` (N ≥ 2) holds only the new or changed work for version N. If the file does not exist, **halt and flag**; never improvise scope.
3. **`/system_architecture/`** — resolve the current version: within this folder only, list files matching `^system_architecture_\d+\.md$`, extract the trailing integer, take the highest. If names do not parse cleanly (non-numeric suffix, gaps, duplicates) **halt and flag**. This pattern deliberately excludes `/essentials/system_architecture_essential_N.md`. Older versions are consulted only to resolve a conflict.
4. **Essentials-vs-architecture drift check:** compare the `Source Architecture Version:` line in the phase's essentials file with the current version from step 3. If they differ, read the **Downstream Impact on Essentials** field of every intervening architecture changelog. All start with `NO_IMPACT` → log it and proceed. Any starts with `IMPACT`, or the field is missing → **halt and flag**.
5. **`/prd/`** — resolve the current PRD with the same rule (`PRD_<digits>.md`, highest integer; halt and flag on ambiguity).
6. **Architecture-vs-PRD drift check:** compare the current architecture's `Derived From: PRD_M.md` line with the current PRD from step 5. If they differ, read the **Downstream Impact** field of every intervening PRD changelog. All `NO_IMPACT` → log and proceed. Any `IMPACT`, or missing → **halt and flag** (a human decides).
7. **`/prd/PRD_N.md` (current)** — cross-reference for any requirements question.

There is no direct essentials-vs-PRD check; the chain in steps 4 and 6 already covers it.

**Version alignment check:** PRD_N ↔ system_architecture_N ↔ essential_N ↔ tracker_N share the same N. **Halt and flag** if the highest-numbered files in `/prd/`, `/system_architecture/` and `/essentials/` do not share one N, or if an essentials file's source lines do not carry its own N. An architecture change always starts with a PRD bump; never create an essentials file per build step.

## 2. Authority and conflicts

- Source of truth order: current `PRD_N.md` → current `system_architecture_N.md` → current essentials file → code.
- Never silently deviate from a decision logged in the current architecture (Decision Log / ADRs) or the current PRD. If a conflict arises, flag it explicitly; do not override it.
- Never start a phase whose essentials file does not exist.
- Never edit a prior PRD or architecture version in place. Changes to architecture or PRD are made in design chat (System Designer), as a new numbered full snapshot with a changelog block.
- Respect system design rules from the project source files and never code in deviation from them. (Note: `SYETEM DESIGN RULES.html` in the project currently contains no rules — see architecture §16; do not rely on it.)

## 3. The 12 non-negotiable fullstack rules (enforced on every task)

1. Understand the problem deeply before designing or coding.
2. Define functional and non-functional requirements clearly.
3. Estimate scale and traffic with back-of-the-envelope math.
4. Design the data model before APIs.
5. Define the API / interface layer explicitly.
6. Design high-level architecture only after the above steps.
7. Deep dive into critical components (schema, caching, queues, storage).
8. Address cross-cutting concerns: observability, security, CI/CD, error handling, idempotency.
9. Branching discipline — never push directly to `main`; always work on a feature branch and open a pull request on GitHub for every change.
10. Apply the Extensibility & Change-Tolerance rules (data model, API, auth, database, feature/module removal) on every change, with the same strictness on every project.
11. Review, challenge and simplify the design.
12. Document and communicate the architecture (ADRs, diagrams, rationale).

## 4. Project-specific hard rules

- **Branches:** work on `feat/…` or `fix/…`; open a PR for every change (including docs). Never push to `main`. Install the committed `pre-push` hook. Commit messages and PR bodies end with the attribution lines the environment specifies.
- **Secrets:** never in code, logs, tests or commits. Two Cloudflare tokens: nightly = D1 only; deploy = used only by `deploy.yml`.
- **Legal gate:** do not enable any `SOURCE_ENABLED_*` flag or fetch from football-data.org / football-data.co.uk until `docs/legal/source_terms_register.md` has a signed entry for it.
- **Source data:** never commit raw CSV/API dumps; tests use synthetic data.
- **Persistence:** SQL only inside `apps/bot/src/repo` and `apps/fit/src/footy/repo`; bound parameters only.
- **Auth:** only the `auth` module reads webhook secrets or the allowlist.
- **Migrations:** forward-only and additive-first; no rename/drop in the same change as its replacement; nothing removed without prior deprecation flag.
- **Numerics:** Python is the reference; TypeScript must match the golden vectors within 1e-9; all markets derive from one grid.
- **CPU gate:** do not exceed the Worker CPU target; if p95 > 6 ms follow the F1 → F3 ladder, and escalate F2/F3 as an architecture change.
- **Idempotency:** `update_id` dedupe; first prediction per `fixture_key` immutable; persist then reply.
- **Scope:** v1 out-of-scope items (architecture §1.4) are not built.

## 5. Tracker discipline

`/tracker/` is owned by Claude Code during implementation. After each working session add a dated entry (date; essentials file, stage and architecture version built against; per-module status `in-progress`/`complete`; open issues). Keep entries append-only. Entries for version N go in `tracker/tracker_N.md`; start `tracker_N.md` when version N's documents are written.

## 6. When unsure

Ask Divine. Do not assume. State what you found, what is unclear, and the options with trade-offs.