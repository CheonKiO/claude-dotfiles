# Code Comprehension Handoff

Read this when: an implementation task or a meaningful chunk of feature work wraps, before moving to the next task or declaring done.

The user must be able to understand the code that was written — not just that it works. A past project failed here: AI-written code the user couldn't read later became an unmaintainable god-component. Treat comprehension as part of "done," not an optional extra.

When implementation wraps, before proceeding, give the user a walkthrough:

- **Reading order** — which files to open first, and the path through them that makes the design click.
- **Per-file role** — what each file does and *why* it exists, not a line-by-line rehash.
- **Data flow** — how one request/action moves through the pieces end to end.
- Pitch it at the user's level and in their language; lead with the shape, then detail.

Then pause and confirm the user actually follows it before continuing to the next task. Their understanding is the gate, not your explanation.

Tools that produce this (optional): the `understand-anything` skills — `understand-explain` (deep-dive one file/module), `understand-onboard` (onboarding guide), `understand`/tour (guided multi-step tour). Use them or write the walkthrough directly, whichever fits the size.
