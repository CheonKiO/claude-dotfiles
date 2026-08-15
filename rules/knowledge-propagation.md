# Knowledge Propagation

Read this when: a design decision is finalized, a feature-sized task wraps up, or you're writing a commit/MR body — i.e. deciding where self-authored docs live and how finished work gets recorded.

Separate personal scratch (PLAN.md, REVIEW.md, session notes) from team-facing docs.

**Self-authored scratch/planning/report docs default to one gitignored staging directory** (e.g. `private/`), not scattered loose at the repo root or inside `docs/`. If the project doesn't have one yet, create it and add a single directory line to `.git/info/exclude` — don't add filenames one at a time as they come up. Exceptions: a file whose location is fixed by tooling (e.g. `CLAUDE.md` must stay at the project root to auto-load; a skill's hardcoded plan/spec path) stays where the tool expects it, individually ignored. This does not apply to code — code always goes in its normal tracked location.

- When a design decision is finalized, propose promoting it from the staging directory into the project's real `docs/` (or wherever the team keeps it) — moving the file out and `git add`-ing it *is* the promotion. Don't let it live only in the staging directory or chat history.
- When a feature-sized task wraps up, propose a short summary: what changed, why, gotchas, files touched.
- Commit/MR bodies explain **what and why**; let the diff speak for **how**.
