# codex-skill-orchestrator

One-skill repository for a portable OpenAI Codex skill:

- `skill-orchestrator/` is the installable skill.
- It bootstraps `AGENTS.md`, a project-local `task-orchestrator`, and compact stack-aware manager skills.
- Stack detection is evidence-based: direct dependencies, manifests, configs, package scripts, and source files, not a closed list of known frameworks.
- Generated skills are intentionally small: they route Codex toward local context, current primary docs when needed, stuck-loop reframing, and project validation commands.
- Task briefs live in `docs/tasks/`; completed task files are renamed with `(closed)` before `.md`.

## Install From This Repo

Ask Codex to install the skill from the GitHub tree URL for the skill folder:

```text
Install the skill from https://github.com/<owner>/codex-skill-orchestrator/tree/main/skill-orchestrator
```

After Codex installs it, restart Codex so the skill is discovered.

## Use In a Project

Then ask:

```text
Use $skill-orchestrator to connect itself to this project.
```

The skill will analyze the project stack and create/update only managed orchestration files. It uses `.codex/skills` when available and falls back to `.skill-orchestrator/skills` if project `.codex` is read-only.
