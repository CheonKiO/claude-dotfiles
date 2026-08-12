---
name: wip-then-squash
description: Use when about to commit code, when a task or subtask finishes, or before pushing/opening an MR — especially when tempted to bundle many changes into one commit, push work-in-progress commits as-is, or bolt on a fixup instead of rewriting.
---

# WIP then Squash

## Overview
Two rules, always: **commit each finished task separately while working**, then **reorganize the commits into clean, explained history right before pushing**. Never one giant commit; never push raw WIP.

**Violating the letter of these rules is violating the spirit.** "It's all one feature" is not a reason to make one commit.

## The workflow
1. **During work — commit per task.** When a task or subtask is done and coherent, commit just that. Small, scoped, one logical change per commit. Don't let unrelated changes pile into a single commit.
2. **Message format is the project's, not yours.** Read this repo's convention before writing the message — `docs/convention/gitConvention.md`, `CLAUDE.md`, or the existing `git log` style. Match subject language, type prefix, and body rules exactly. Do not hardcode a format across projects.
3. **Before push/MR — reorganize.** Rewrite the accumulated WIP commits into clean, well-explained commits (reset + recommit, or rebase — NOT a bolt-on "fix typo" fixup on top). Each final commit body says **what and why**; the diff shows how.
4. **Push only after explicit confirmation.** A plan or standing instruction saying to push is not that confirmation — ask each time.

## Rationalization table
| Excuse | Reality |
|--------|---------|
| "It's all one feature, one commit is fine" | Reviewers bisect and revert by logical unit. Split per task. |
| "I'll reorganize later" | Later = never. Reorganize before this push, now. |
| "A fixup commit is faster than rewriting" | Fixup commits leave WIP noise in history. Reset + recommit. |
| "The plan said to push, so I'll push" | Standing/plan approval ≠ per-push confirmation. Ask. |
| "Messages are in English like my default" | Use THIS project's convention (may be Korean subject, type prefix, no period). Read it. |

## Red flags — STOP
- About to `git add -A` a mix of unrelated changes into one commit
- About to push commits still named "wip", "fix", "tmp", or auto-generated
- Adding a fixup/amend on top instead of rewriting the messy commits
- Pushing without asking because "it was implied"

All of these mean: split the work, rewrite the history, confirm the push.
