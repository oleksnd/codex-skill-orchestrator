#!/usr/bin/env python3
"""Bootstrap project-local orchestration files for Codex."""

from __future__ import annotations

import argparse
import json
import os
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analyze_project import analyze_project


MANAGED_MARKER = "<!-- managed-by: skill-orchestrator -->"
BLOCK_START = "<!-- skill-orchestrator:start -->"
BLOCK_END = "<!-- skill-orchestrator:end -->"


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def choose_layout(project: Path, local_dir: str) -> dict[str, Path]:
    if local_dir != "auto":
        base = project / local_dir
    else:
        codex_dir = project / ".codex"
        if codex_dir.exists() and not os.access(codex_dir, os.W_OK):
            base = project / ".skill-orchestrator"
        else:
            base = codex_dir

    manifest = base / "skill-orchestrator" / "manifest.json" if base.name == ".codex" else base / "manifest.json"
    return {
        "base": base,
        "skills": base / "skills",
        "manifest": manifest,
    }


def task_orchestrator_skill(task_dir: str) -> str:
    description = (
        "Project-local task orchestration. Use at the start of a new standalone task or new chat "
        "when the user introduces a fresh feature, bug, refactor, architecture question, or project idea. "
        "Store task briefs as Markdown files in docs/tasks and mark completed task filenames with (closed). "
        "Do not use when the user is continuing, resuming, asking status, asking to keep going, fixing/testing "
        "the previous work, or refining an already-defined task."
    )
    return textwrap.dedent(
        f"""\
        ---
        name: task-orchestrator
        description: {yaml_string(description)}
        ---

        {MANAGED_MARKER}

        # Task Orchestrator

        ## Gate

        First decide whether the user's request is a new standalone objective or a continuation.

        Treat as continuation when the user says to continue/resume/keep going, asks for status, refers to the previous task, asks to fix/test the last change, returns after context compaction, or narrows an already-defined task. Do not create a new task brief in those cases.

        Treat as new when the user introduces a fresh feature, bug, refactor, idea, architecture decision, or broad implementation request.

        ## For New Tasks

        Use `{task_dir}/` for task files. Create this directory if it does not exist.

        Create one Markdown file per standalone task:

        - filename format: `YYYY-MM-DD-short-task-slug.md`
        - keep active tasks without a status marker in the filename
        - do not store task briefs in `.codex/`, `.agents/`, or other hidden system folders

        The file should contain:

        - task title and date
        - status: `open`
        - problem statement
        - goals and non-goals
        - known constraints from the repo/user
        - ordered todos
        - verification plan
        - open questions only when a risky assumption cannot be resolved locally

        Then work from that brief. Keep it short enough to be useful in a future chat.

        ## Closing Tasks

        When the task is finished and verified, update the task file status to `closed`, add a short completion note, and rename the file by appending `(closed)` before `.md`.

        Example: `{task_dir}/2026-05-24-add-auth.md` -> `{task_dir}/2026-05-24-add-auth (closed).md`

        ## For Continuations

        Look in `{task_dir}/` for the relevant open task file. Treat filenames containing `(closed)` as finished history. Continue the existing plan, updating status only when it helps future recovery. Do not rewrite the brief as a new task.
        """
    )


def stack_skill(spec: dict[str, Any]) -> str:
    display = spec["display"]
    skill_name = spec["skill_name"]
    docs = spec.get("docs") or []
    research_queries = spec.get("research_queries") or [f"{display} official documentation"]
    if docs:
        research = "\n".join(f"- {url}" for url in docs)
    else:
        research = "\n".join(f"- {query}" for query in research_queries[:4])
    checks = ", ".join(spec.get("checks") or ["the closest existing test/lint/build command"])
    signals = "\n".join(f"- {signal}" for signal in spec.get("signals", [])[:8])
    description = (
        f"Compact project-local manager for {display} work in this repository. Use when a task touches "
        f"{spec['triggers']}. For simple obvious edits, proceed from local context; for complex, ambiguous, "
        f"failing, new, deployment-sensitive, security-sensitive, or version-sensitive {display} work, inspect "
        "local patterns and current official documentation or primary sources before implementation."
    )
    return textwrap.dedent(
        f"""\
        ---
        name: {skill_name}
        description: {yaml_string(description)}
        ---

        {MANAGED_MARKER}

        # {display} Orchestrator

        ## Route

        Use this as a behavior manager, not a tutorial or API summary.

        - Inspect local versions, configs, conventions, nearby code, and existing tests first.
        - For simple, obvious edits, implement directly from local context.
        - For complex, ambiguous, failing, new, security-sensitive, deployment-sensitive, or version-sensitive work, look up current official docs, release notes, repository docs, or another primary source before changing code.
        - If you get stuck or repeat a failed approach, stop and reframe: inspect a smaller local reproduction, search the relevant docs/issues, then choose a new path.
        - Prefer this repo's patterns over generic preferences.
        - Validate with {checks}.
        - Do not spend context explaining what {display} is; use research only to improve the implementation decision.

        ## Local Signals

        {signals or "- Detected from project manifests, configs, scripts, or source files."}

        ## Research Cues

        {research}
        """
    )


def agents_block(skills: list[dict[str, Any]], skills_dir: Path, project: Path) -> str:
    task_skill_path = relative(skills_dir / "task-orchestrator" / "SKILL.md", project)
    lines = [
        BLOCK_START,
        "## Skill Orchestrator",
        "",
        f"- For a new standalone task, read `{task_skill_path}` before implementation and create/update the task brief in `docs/tasks/`.",
        "- For a continuation, resume the existing task; do not create a new brief just because the chat is new.",
        "- For stack-specific work, read the relevant compact local skill before acting.",
    ]
    if skills:
        lines.extend(
            f"- {item['display']}: `{relative(skills_dir / item['skill_name'] / 'SKILL.md', project)}`"
            for item in skills
        )
    else:
        lines.append("- No stack-specific skills were detected yet; rerun the bootstrap after dependencies/configs exist.")
    lines.extend(
        [
            "- These local skills are managers, not tutorials. Use them to decide when to inspect local code, official docs, and validation commands.",
            "- If project-local skills are not auto-discovered by the current Codex runtime, route by reading the listed `SKILL.md` files manually.",
            BLOCK_END,
        ]
    )
    return "\n".join(lines)


def upsert_agents(existing: str, block: str) -> str:
    if BLOCK_START in existing and BLOCK_END in existing:
        pattern = re.compile(
            r"^[ \t]*" + re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"[ \t]*",
            re.DOTALL | re.MULTILINE,
        )
        return pattern.sub(block, existing).rstrip() + "\n"
    prefix = existing.rstrip()
    if prefix:
        return prefix + "\n\n" + block + "\n"
    return block + "\n"


def write_managed(path: Path, content: str, dry_run: bool, changes: list[str]) -> None:
    if path.exists():
        old = path.read_text(encoding="utf-8", errors="ignore")
        if old == content:
            changes.append(f"unchanged {path}")
            return
        if MANAGED_MARKER not in old:
            changes.append(f"skipped custom file {path}")
            return
        action = "update"
    else:
        action = "create"

    changes.append(f"{action} {path}")
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def write_text(path: Path, content: str, dry_run: bool, changes: list[str]) -> None:
    if path.exists() and path.read_text(encoding="utf-8", errors="ignore") == content:
        changes.append(f"unchanged {path}")
        return
    changes.append(("update " if path.exists() else "create ") + str(path))
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def ensure_directory(path: Path, dry_run: bool, changes: list[str]) -> None:
    if path.is_dir():
        changes.append(f"unchanged {path}")
        return
    changes.append(f"create directory {path}")
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def bootstrap(project: Path, dry_run: bool, max_stack_skills: int, local_dir: str) -> dict[str, Any]:
    project = project.resolve()
    report = analyze_project(project)
    selected = report["detected"][:max_stack_skills]
    layout = choose_layout(project, local_dir)
    skills_dir = layout["skills"]
    task_dir = project / "docs" / "tasks"
    task_dir_label = relative(task_dir, project)
    changes: list[str] = []

    ensure_directory(task_dir, dry_run, changes)

    write_managed(
        skills_dir / "task-orchestrator" / "SKILL.md",
        task_orchestrator_skill(task_dir_label),
        dry_run,
        changes,
    )

    for spec in selected:
        write_managed(
            skills_dir / spec["skill_name"] / "SKILL.md",
            stack_skill(spec),
            dry_run,
            changes,
        )

    agents_path = project / "AGENTS.md"
    existing_agents = agents_path.read_text(encoding="utf-8", errors="ignore") if agents_path.exists() else ""
    write_text(agents_path, upsert_agents(existing_agents, agents_block(selected, skills_dir, project)), dry_run, changes)

    manifest = {
        "generated_by": "skill-orchestrator",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project),
        "dry_run": dry_run,
        "local_base": relative(layout["base"], project),
        "package_managers": report["package_managers"],
        "generated_skills": ["task-orchestrator"] + [item["skill_name"] for item in selected],
        "detected": report["detected"],
    }
    if not dry_run:
        write_text(
            layout["manifest"],
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            dry_run,
            changes,
        )
    else:
        changes.append(f"dry-run skip {layout['manifest']}")

    return {
        "project_root": str(project),
        "dry_run": dry_run,
        "local_base": relative(layout["base"], project),
        "changes": changes,
        "detected": selected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="Project root to bootstrap")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing")
    parser.add_argument("--max-stack-skills", type=int, default=12, help="Maximum stack skills to generate")
    parser.add_argument(
        "--local-dir",
        default="auto",
        help="Where to place local orchestration files: auto, .codex, .skill-orchestrator, or another relative path",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    result = bootstrap(Path(args.project), args.dry_run, args.max_stack_skills, args.local_dir)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        mode = "DRY RUN" if args.dry_run else "APPLIED"
        print(f"{mode}: {result['project_root']}")
        print(f"Local base: {result['local_base']}")
        print("Detected stack:")
        if result["detected"]:
            for item in result["detected"]:
                print(f"- {item['display']} -> {item['skill_name']}")
        else:
            print("- none")
        print("Changes:")
        for change in result["changes"]:
            print(f"- {change}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
