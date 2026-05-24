---
name: skill-orchestrator
description: "Project-level skill orchestration for OpenAI Codex. Use when connecting this repository's skill to a project, bootstrapping AGENTS.md instructions, detecting a repository's stack from local manifests/configs/dependencies/scripts, generating compact project-local manager skills for detected technologies/plugins/tools/services, or setting up a task-orchestrator that turns only new standalone user tasks into concise technical briefs without retriggering on continuations."
---

# Skill Orchestrator

## Purpose

Install a small project-local routing layer: `AGENTS.md`, a default `task-orchestrator`, and compact stack skills for detected project stack signals. Generated stack skills must manage agent behavior, not teach technology basics.

## Connect to a Project

1. Identify the target project root. Use the current workspace unless the user points elsewhere.
2. Run a dry run first:

```bash
python3 <this-skill>/scripts/bootstrap_project.py --project <project-root> --dry-run
```

3. If the plan is reasonable, run:

```bash
python3 <this-skill>/scripts/bootstrap_project.py --project <project-root>
```

4. Review the reported files. If an obvious stack was missed, improve the manifest/config/dependency signal detection in `scripts/analyze_project.py` rather than adding a closed technology catalog.

The bootstrap is idempotent. It updates only managed files/blocks and skips existing custom skill files it does not own.

## Generated Files

- `AGENTS.md`: adds a managed routing block so Codex knows when to read local orchestrator skills.
- `.codex/skills/task-orchestrator/SKILL.md`: default task gate for new standalone tasks.
- `.codex/skills/<technology>-orchestrator/SKILL.md`: compact manager skills for detected dependencies, configs, tools, plugins, services, or ecosystems.
- `.codex/skill-orchestrator/manifest.json`: detected stack and generated skill inventory.
- `docs/tasks/`: user-visible Markdown task briefs created by `task-orchestrator`.

If project `.codex/` already exists but is read-only, bootstrap uses `.skill-orchestrator/skills` and `.skill-orchestrator/manifest.json` instead. Project-local skills are routed through `AGENTS.md`; if the current Codex runtime auto-discovers them, use normal skill triggering, otherwise read the matching local `SKILL.md` when the routing block says to.

## Task Orchestrator Rule

Use `task-orchestrator` only when the user starts a new standalone objective: a fresh feature, bug, refactor, project idea, architecture decision, or unclear implementation request.

Do not trigger it when the user is continuing or resuming prior work, asks for status, says to keep going, asks to fix/test the previous change, returns after compaction, or refines an already-defined task. In those cases continue from the existing context and update the existing plan or task brief only if useful.

For a new task, produce a concise technical brief before implementation:

- create `docs/tasks/` if it does not exist
- create one `docs/tasks/YYYY-MM-DD-short-task-slug.md` file per standalone task
- keep active tasks without a status marker in the filename
- problem statement
- concrete goals and non-goals
- relevant project constraints
- ordered todos with verification steps
- open questions only when a risky assumption cannot be resolved from the repo

When a task is finished and verified, update its status to `closed`, add a short completion note, and rename the file by appending `(closed)` before `.md` so the user can manually delete completed tasks later.

## Stack Skill Rule

Generated stack skills should be tiny managers:

- First inspect local versions, configs, conventions, nearby code, and tests.
- For simple, obvious edits, proceed from local context.
- For new, complex, failing, ambiguous, security-sensitive, deployment-sensitive, or version-sensitive work, check official documentation or primary sources before implementing.
- If the agent gets stuck or repeats a failed approach, force a reset: isolate the local signal, search current docs/issues, and choose a different implementation path.
- Prefer project patterns over generic preferences.
- Validate with the project's existing commands.
- Avoid tutorials, long API explanations, and generic facts Codex already knows.

Read `references/compact-skill-rules.md` only when changing the generated skill style or adding new templates.

## Useful Commands

Analyze without writing:

```bash
python3 <this-skill>/scripts/analyze_project.py --project <project-root>
```

Write integration files:

```bash
python3 <this-skill>/scripts/bootstrap_project.py --project <project-root>
```
