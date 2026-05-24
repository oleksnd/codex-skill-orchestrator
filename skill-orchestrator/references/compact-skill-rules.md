# Compact Skill Rules

Use this reference only when editing generated templates or stack-signal detection.

## What Generated Skills Are

Generated stack skills are routing and judgment helpers. They remind Codex when to rely on local context, when to consult official documentation, and how to validate changes in this project.

They are not course notes, API summaries, or technology introductions.

## Required Shape

- Keep each generated skill under roughly 80 lines.
- Put trigger wording in YAML `description`; Codex uses metadata before the body is loaded.
- Keep the body imperative and procedural.
- Include official docs links when they are known from reliable local evidence; otherwise include concise research cues that tell Codex to find official docs or another primary source for the exact local package/config/version.
- Name files as `.codex/skills/<technology>-orchestrator/SKILL.md` when `.codex` is writable; use `.skill-orchestrator/skills/<technology>-orchestrator/SKILL.md` as the fallback.
- Include `<!-- managed-by: skill-orchestrator -->` so bootstrap can update owned files safely.

## Default Decision Rule

- Simple and obvious: inspect local code, edit, validate.
- Complex, unclear, failing, new, security-sensitive, deployment-sensitive, or version-sensitive: inspect local code and official docs before editing.
- Repeated failure or loop: stop, reframe the problem, inspect smaller local evidence, and consult current docs/issues before trying another implementation.
- New standalone task: create/update a Markdown task brief in `docs/tasks/`.
- Continuation of previous work: continue the current open task, do not recreate planning artifacts.
- Finished task: mark status as `closed` and append `(closed)` before `.md` in the filename.

## Anti-Patterns

- Explaining what a framework is.
- Listing common APIs without a project-specific reason.
- Maintaining a closed list of every possible technology, framework, server, plugin, or hosted platform.
- Creating long generic best-practices essays.
- Replacing local conventions with generic preferences.
- Triggering documentation lookup for every tiny edit.
