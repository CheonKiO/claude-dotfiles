---
name: delegation-tiering
description: Use when deciding whether to delegate work to a subagent (Agent tool) and which model tier to assign — before spawning any agent. Covers the delegate-vs-inline call, the model-tier table, the account-plan headroom check that shifts tiers, and the post-subagent gitignored-file check.
---

# Subagent Delegation & Model Tiering

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

**Account check** — read `claudeAiOauth.subscriptionType` from `~/.claude/.credentials.json` (never print its token fields, only this plan label). `team`, `max`, or `enterprise` uses the table above as-is (full headroom). `pro`, `free`, or anything else/unrecognized shifts every tier down one (haiku/sonnet/opus), no review exception — less headroom, so default to the cheaper tier. Note: this field is cached at login and can lag a real plan change until the next re-login (anthropics/claude-code#43639) — if a tier change doesn't seem to be taking effect, ask the user whether they've re-logged in since upgrading.

Run independent delegations in parallel (multiple Agent calls in one message) rather than sequentially.

**After a subagent finishes**, check whether gitignored files (`.env`, etc.) changed. `git diff` never shows this — check explicitly.
