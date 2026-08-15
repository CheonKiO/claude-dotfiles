# Git / Work Hygiene

Read this around merges, rebases, and branch/worktree cleanup.

- Propose cleaning up branches/worktrees right after a merge lands — zombies left to accumulate cost far more to untangle later. (For worktree removal see the `worktree-cleanup` skill; for integrating a finished branch see `finishing-a-development-branch`.)
- If a rebase is about to make commits unreachable from any branch, flag it before doing it — those commits stop being citable evidence.

Note: the post-subagent gitignored-file check now lives in the `delegation-tiering` skill.
