# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## Situational references (read on demand)

The rules below apply every turn. These apply only in specific situations — read the file/skill when you hit the trigger, then fold it into your judgment.

| Trigger | Where |
|---|---|
| About to spawn a subagent / pick a model tier | `delegation-tiering` skill (auto) |
| Design finalized · feature wraps · writing commit/MR body | `~/.claude/rules/knowledge-propagation.md` |
| Asked to review/read a long existing document | `~/.claude/rules/doc-review.md` |
| Around merges, rebases, branch/worktree cleanup | `~/.claude/rules/git-hygiene.md` |

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

## 5. Verification Loop First

**Don't generate code in an area that has no way to verify it.**

Before writing the first code in a new area (new app, package, or frontend module), check:
- [ ] Can this area's code be verified automatically (test runner, type check, lint)?
- [ ] If not, set that up first. If it takes more than half a day, tell the user before proceeding.

Why: AI makes code nearly free to add. Without a verification loop, debt piles up exactly as fast as the code does. Real case: same project, same author — the backend (580 tests) graded A; the frontend (0 tests) became a 3,500-line god component. Not a skill gap — a loop gap.

**Don't declare something "done" without verification.** Cite the test/build output as evidence, not a claim.

## 6. Structural Guardrails

Without instruction, AI defaults to appending to the file that's already open — it's the path of least resistance, not a judgment call. Counteract with defaults:

- **No more additions past ~500 lines.** Split first, or propose a split and get confirmation.
- **Pure functions live outside component/class files.** They need to be independently testable.
- **A new hook or new responsibility gets a new file** — don't stack it on an existing one.
- If a file you're about to touch is already over the limit, say so before starting.

"Move fast now, clean up later" doesn't happen — treat later as never.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
