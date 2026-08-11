# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

When writing to a path that already has content (a doc, a report, notes):
- Default to append, not overwrite, unless the user explicitly asked for a fresh rewrite/replacement.
- Read it first regardless — a bare shell `mv`/`cp` over an existing path skips that check and has destroyed unrecoverable notes before.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Subagent Delegation & Model Tiering

**Delegate by default. Match model to task difficulty.**

This overrides the harness default of "don't spawn agents unless asked" — delegate proactively when a task fits the criteria below, without waiting for the user to request it.

Delegate to a subagent (Agent tool) when a task is independent/parallelizable, exploratory, a scoped implementation, or review/verification. Keep it inline when it needs tight back-and-forth with the user, is a 1-2 line trivial edit, or depends heavily on context from the immediately preceding turns.

**Model tiers** — set the `model` param on the Agent tool call explicitly (pick whichever `subagent_type` otherwise fits the task; this just fixes the model).

| Difficulty | Model |
|---|---|
| Simple / mechanical | `sonnet` |
| Standard (exploration, multi-file edits, feature work) | `opus` |
| High difficulty (architecture, hard-to-reproduce bugs, high-stakes calls) | `opus` |
| **Review / verification** (diff/branch/task review) | **`fable`** |

**Account check** — read `rateLimitTier` from `~/.claude/.credentials.json` (never print its token fields, only this label — it directly reflects usage headroom, more precisely than `subscriptionType`). A `max` tier (e.g. `default_claude_max_5x`, `default_claude_max_20x`) uses the table above as-is. `default_claude_pro` or anything else/unrecognized shifts every tier down one (haiku/sonnet/opus), no review exception — less headroom, so default to the cheaper tier. Note: this field is cached at login and can lag a real plan change until the next re-login (anthropics/claude-code#43639) — if a tier change doesn't seem to be taking effect, ask the user whether they've re-logged in since upgrading.

Run independent delegations in parallel (multiple Agent calls in one message) rather than sequentially.

## 6. Verification Loop First

**Don't generate code in an area that has no way to verify it.**

Before writing the first code in a new area (new app, package, or frontend module), check:
- [ ] Can this area's code be verified automatically (test runner, type check, lint)?
- [ ] If not, set that up first. If it takes more than half a day, tell the user before proceeding.

Why: AI makes code nearly free to add. Without a verification loop, debt piles up exactly as fast as the code does. Real case: same project, same author — the backend (580 tests) graded A; the frontend (0 tests) became a 3,500-line god component. Not a skill gap — a loop gap.

**Don't declare something "done" without verification.** Cite the test/build output as evidence, not a claim.

## 7. Structural Guardrails

Without instruction, AI defaults to appending to the file that's already open — it's the path of least resistance, not a judgment call. Counteract with defaults:

- **No more additions past ~500 lines.** Split first, or propose a split and get confirmation.
- **Pure functions live outside component/class files.** They need to be independently testable.
- **A new hook or new responsibility gets a new file** — don't stack it on an existing one.
- If a file you're about to touch is already over the limit, say so before starting.

"Move fast now, clean up later" doesn't happen — treat later as never.

## 8. Knowledge Propagation

Separate personal scratch (PLAN.md, REVIEW.md, session notes) from team-facing docs.

**Self-authored scratch/planning/report docs default to one gitignored staging directory** (e.g. `private/`), not scattered loose at the repo root or inside `docs/`. If the project doesn't have one yet, create it and add a single directory line to `.git/info/exclude` — don't add filenames one at a time as they come up. Exceptions: a file whose location is fixed by tooling (e.g. `CLAUDE.md` must stay at the project root to auto-load; a skill's hardcoded plan/spec path) stays where the tool expects it, individually ignored. This does not apply to code — code always goes in its normal tracked location.

- When a design decision is finalized, propose promoting it from the staging directory into the project's real `docs/` (or wherever the team keeps it) — moving the file out and `git add`-ing it *is* the promotion. Don't let it live only in the staging directory or chat history.
- When a feature-sized task wraps up, propose a short summary: what changed, why, gotchas, files touched.
- Commit/MR bodies explain **what and why**; let the diff speak for **how**.

## 9. Work Hygiene

- Propose cleaning up branches/worktrees right after a merge lands — zombies left to accumulate cost far more to untangle later.
- If a rebase is about to make commits unreachable from any branch, flag it before doing it — those commits stop being citable evidence.
- After a subagent finishes, check whether gitignored files (`.env`, etc.) changed. `git diff` never shows this — check explicitly.

## 10. Document Review Digest

**When asked to review/read a long document, always lead with a short plain-language summary before anything else.** The user may not have read the whole thing — don't assume they did.

- Open with what the document is about and its 3-5 main points, in accessible language (not a wall of jargon).
- Then go into detail/findings if needed. Detail follows the summary, never replaces it.
- This applies to reviewing existing docs (specs, reviews, retrospectives), not to documents you just wrote yourself in this turn.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

@RTK.md
