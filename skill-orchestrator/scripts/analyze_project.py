#!/usr/bin/env python3
"""Detect project stack signals and recommend compact local manager skills.

The analyzer intentionally avoids a closed catalog of technologies. Instead it
derives stack candidates from the evidence already present in the repository:
direct dependencies, manifests, config filenames, package scripts, and source
files. Generated skills can then act as coordinators for the detected stack
pieces without needing this script to know every framework, plugin, server, or
tool in advance.
"""

from __future__ import annotations

import argparse
import hashlib
import fnmatch
import json
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback.
    tomllib = None  # type: ignore[assignment]


EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    ".vercel",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

PACKAGE_SECTION_PRIORITY = {
    "dependencies": 62,
    "project.dependencies": 62,
    "require": 62,
    "tool.poetry.dependencies": 62,
    "devDependencies": 46,
    "project.optional-dependencies": 44,
    "dependency-groups": 44,
    "dev-dependencies": 42,
    "require-dev": 42,
    "peerDependencies": 38,
    "optionalDependencies": 34,
}

ROOT_CONFIG_EXCLUDES = {
    "package",
    "package-lock",
    "pnpm-lock",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "composer.lock",
    "cargo.lock",
    "poetry.lock",
    "uv.lock",
    "gemfile.lock",
    "manifest",
}

GENERIC_SCOPED_PARTS = {
    "adapter",
    "client",
    "cli",
    "config",
    "core",
    "framework",
    "kit",
    "node",
    "plugin",
    "preset",
    "runtime",
    "sdk",
    "server",
    "test",
    "testing",
    "types",
}

COMMAND_STOPWORDS = {
    "and",
    "bun",
    "cp",
    "echo",
    "mkdir",
    "npm",
    "npx",
    "pnpm",
    "rm",
    "run",
    "then",
    "yarn",
}

SCRIPT_WRAPPERS = {
    "cross-env",
    "env",
}

RUNTIME_COMMANDS = {
    "bash",
    "node",
    "python",
    "python3",
    "sh",
}

PACKAGE_RUNNERS = {
    "bun",
    "npm",
    "npx",
    "pnpm",
    "yarn",
}

VALIDATION_SCRIPT_NAMES = (
    "typecheck",
    "type-check",
    "check",
    "lint",
    "test",
    "test:unit",
    "test:e2e",
    "e2e",
    "build",
    "ci",
)

LANGUAGE_EXTENSIONS = {
    ".py": ("python", "Python"),
    ".js": ("javascript", "JavaScript"),
    ".jsx": ("jsx", "JSX"),
    ".ts": ("typescript", "TypeScript"),
    ".tsx": ("tsx", "TSX"),
    ".go": ("go", "Go"),
    ".rs": ("rust", "Rust"),
    ".rb": ("ruby", "Ruby"),
    ".php": ("php", "PHP"),
    ".java": ("java", "Java"),
    ".kt": ("kotlin", "Kotlin"),
    ".cs": ("csharp", "C#"),
    ".swift": ("swift", "Swift"),
    ".scala": ("scala", "Scala"),
    ".ex": ("elixir", "Elixir"),
    ".exs": ("elixir", "Elixir"),
}

PACKAGE_MANAGER_MARKERS = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
    ("uv.lock", "uv"),
    ("poetry.lock", "poetry"),
)


@dataclass
class Candidate:
    key: str
    display: str
    kind: str
    priority: int = 0
    score: int = 0
    signals: set[str] = field(default_factory=set)
    research_terms: set[str] = field(default_factory=set)
    checks: set[str] = field(default_factory=set)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_text(path: Path, limit: int = 250_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except Exception:
        return ""


def collect_files(root: Path, max_files: int) -> list[str]:
    files: list[str] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".cache")]
        rel_dir = Path(current).relative_to(root)
        for name in names:
            rel = (rel_dir / name).as_posix() if rel_dir.as_posix() != "." else name
            files.append(rel)
            if len(files) >= max_files:
                return files
    return files


def any_file(files: set[str], *patterns: str) -> bool:
    return any(any(fnmatch.fnmatch(path, pattern) for pattern in patterns) for path in files)


def stable_slug(value: str, max_length: int = 64) -> str:
    slug = value.lower().strip()
    slug = slug.replace("@", "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if not slug:
        slug = "stack-item"
    if len(slug) <= max_length:
        return slug
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:8]
    return f"{slug[: max_length - 9].rstrip('-')}-{digest}"


def pretty_display(value: str) -> str:
    value = value.strip()
    if not value:
        return "Detected Stack Item"
    if value.startswith("@") or "/" in value:
        return value
    words = re.split(r"[-_\s]+", value)
    acronyms = {
        "api",
        "cli",
        "css",
        "db",
        "html",
        "http",
        "js",
        "json",
        "orm",
        "sdk",
        "sql",
        "ts",
        "ui",
        "url",
        "xml",
        "yaml",
    }
    titled = []
    for word in words:
        lower = word.lower()
        if not word:
            continue
        if lower in acronyms:
            titled.append(lower.upper())
        elif lower.endswith("js") and len(lower) > 2:
            titled.append(lower[:-2].capitalize() + "JS")
        else:
            titled.append(word[:1].upper() + word[1:])
    return " ".join(titled) or value


def package_topic(package_name: str) -> tuple[str, str]:
    name = package_name.strip()
    lower = name.lower()
    if lower.startswith("@types/"):
        target = name.split("/", 1)[1]
        return stable_slug(target), pretty_display(target)
    if lower.startswith("@") and "/" in lower:
        scope, package = lower[1:].split("/", 1)
        if package in GENERIC_SCOPED_PARTS or package == scope or package.startswith(f"{scope}-"):
            return stable_slug(scope), pretty_display(scope)
        return stable_slug(f"{scope}-{package}"), name
    return stable_slug(lower), pretty_display(name)


def add_candidate(
    candidates: dict[str, Candidate],
    raw_name: str,
    *,
    signal: str,
    priority: int,
    kind: str,
    display: str | None = None,
    research_terms: Iterable[str] = (),
    checks: Iterable[str] = (),
) -> Candidate:
    key = stable_slug(raw_name)
    candidate = candidates.get(key)
    if candidate is None:
        candidate = Candidate(key=key, display=display or pretty_display(raw_name), kind=kind)
        candidates[key] = candidate
    elif display and (len(display) < len(candidate.display) or candidate.display == pretty_display(candidate.key)):
        candidate.display = display

    candidate.priority = max(candidate.priority, priority)
    candidate.score += priority
    candidate.signals.add(signal)
    candidate.research_terms.update(term for term in research_terms if term)
    candidate.checks.update(check for check in checks if check)
    return candidate


def add_package_candidate(
    candidates: dict[str, Candidate],
    package_name: str,
    *,
    section: str,
    source: str,
    version: str | None = None,
    scripts: dict[str, str] | None = None,
) -> None:
    topic, display = package_topic(package_name)
    priority = PACKAGE_SECTION_PRIORITY.get(section, 40)
    version_label = f"@{version}" if version else ""
    signal = f"{source}: {section} declares `{package_name}{version_label}`"
    checks = matching_script_checks(scripts or {}, {topic, stable_slug(package_name), package_name.lower()})
    if checks:
        priority += 12
    add_candidate(
        candidates,
        topic,
        signal=signal,
        priority=priority,
        kind="package",
        display=display,
        research_terms={package_name, display},
        checks=checks,
    )


def package_data(root: Path, files: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    deps: dict[str, str] = {}
    scripts: dict[str, str] = {}
    for rel in files:
        if not rel.endswith("package.json"):
            continue
        data = read_json(root / rel)
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            for name, version in data.get(section, {}).items():
                deps.setdefault(name, str(version))
        for name, command in data.get("scripts", {}).items():
            scripts.setdefault(name, str(command))
    return deps, scripts


def normalize_command_token(value: str) -> str:
    cleaned = value.strip("'\"`(){}[];,")
    if not cleaned or cleaned.startswith(("-", "$")) or "=" in cleaned:
        return ""
    if "/" in cleaned and not cleaned.startswith("@"):
        return ""
    if cleaned.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".rb", ".go", ".rs")):
        return ""
    return stable_slug(cleaned)


def script_tokens(command: str) -> set[str]:
    segments = re.split(r"\s*(?:&&|\|\||;|\|)\s*", command)
    tokens: set[str] = set()
    for segment in segments:
        tokens.update(script_segment_tokens(segment))
    return tokens


def script_segment_tokens(segment: str) -> set[str]:
    try:
        parts = shlex.split(segment)
    except ValueError:
        parts = segment.split()

    tokens: set[str] = set()
    index = 0
    while index < len(parts):
        token = normalize_command_token(parts[index])
        index += 1
        if not token:
            continue

        if token in SCRIPT_WRAPPERS:
            continue

        if token in RUNTIME_COMMANDS:
            if token.startswith("python") and index + 1 < len(parts) and parts[index] == "-m":
                module = normalize_command_token(parts[index + 1])
                if module and module not in COMMAND_STOPWORDS:
                    tokens.add(module)
            break

        if token in PACKAGE_RUNNERS:
            if index < len(parts):
                runner_action = normalize_command_token(parts[index])
                if token == "npx":
                    continue
                if runner_action in {"dlx", "exec", "x"}:
                    index += 1
                    continue
            break

        if token in COMMAND_STOPWORDS or token in VALIDATION_SCRIPT_NAMES:
            break

        tokens.add(token)
        break
    return tokens


def matching_script_checks(scripts: dict[str, str], terms: set[str]) -> set[str]:
    normalized_terms = {stable_slug(term) for term in terms if term}
    matches: set[str] = set()
    for name, command in scripts.items():
        name_slug = stable_slug(name)
        command_tokens = script_tokens(command)
        if name_slug in normalized_terms or command_tokens.intersection(normalized_terms):
            matches.add(f"package script `{name}`")
    return matches


def validation_checks(scripts: dict[str, str]) -> list[str]:
    checks: list[str] = []
    for name in VALIDATION_SCRIPT_NAMES:
        if name in scripts:
            checks.append(f"package script `{name}`")
    return checks[:5]


def package_json_signals(root: Path, files: list[str], candidates: dict[str, Candidate]) -> dict[str, str]:
    all_scripts: dict[str, str] = {}
    package_json_files = [rel for rel in files if rel.endswith("package.json")]
    for rel in package_json_files:
        data = read_json(root / rel)
        scripts = {name: str(command) for name, command in data.get("scripts", {}).items()}
        all_scripts.update({name: command for name, command in scripts.items() if name not in all_scripts})
        add_candidate(
            candidates,
            "javascript-node-project",
            signal=f"{rel}: package manifest",
            priority=36,
            kind="ecosystem",
            display="JavaScript/Node project",
            research_terms={"package.json", "Node.js package scripts"},
            checks=validation_checks(scripts),
        )
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            for name, version in data.get(section, {}).items():
                add_package_candidate(
                    candidates,
                    str(name),
                    section=section,
                    source=rel,
                    version=str(version),
                    scripts=scripts,
                )
        for script_name, command in scripts.items():
            for token in script_tokens(command):
                if len(token) < 2:
                    continue
                add_candidate(
                    candidates,
                    token,
                    signal=f"{rel}: script `{script_name}` invokes `{token}`",
                    priority=38,
                    kind="script-tool",
                    display=pretty_display(token),
                    research_terms={token},
                    checks={f"package script `{script_name}`"},
                )
    return all_scripts


def parse_requirement_name(raw: str) -> str | None:
    line = raw.strip()
    if not line or line.startswith("#") or line.startswith(("-r ", "--")):
        return None
    egg_match = re.search(r"[#&]egg=([A-Za-z0-9_.-]+)", line)
    if egg_match:
        return egg_match.group(1)
    line = line.split("#", 1)[0].split(";", 1)[0].strip()
    match = re.match(r"([A-Za-z0-9_.-]+)", line)
    return match.group(1) if match else None


def add_python_requirement(
    candidates: dict[str, Candidate],
    requirement: str,
    *,
    section: str,
    source: str,
) -> None:
    name = parse_requirement_name(requirement)
    if not name or name.lower() == "python":
        return
    add_package_candidate(candidates, name, section=section, source=source)


def pyproject_signals(root: Path, files: list[str], candidates: dict[str, Candidate]) -> None:
    pyproject_files = [rel for rel in files if rel.endswith("pyproject.toml")]
    for rel in pyproject_files:
        data = read_toml(root / rel)
        add_candidate(
            candidates,
            "python-project",
            signal=f"{rel}: Python project manifest",
            priority=38,
            kind="ecosystem",
            display="Python project",
            research_terms={"pyproject.toml", "Python packaging"},
        )
        for requirement in data.get("project", {}).get("dependencies", []) or []:
            add_python_requirement(candidates, str(requirement), section="project.dependencies", source=rel)
        optional = data.get("project", {}).get("optional-dependencies", {}) or {}
        for group, requirements in optional.items():
            for requirement in requirements or []:
                add_python_requirement(
                    candidates,
                    str(requirement),
                    section="project.optional-dependencies",
                    source=f"{rel} [{group}]",
                )

        poetry = data.get("tool", {}).get("poetry", {}) or {}
        for name, version in (poetry.get("dependencies", {}) or {}).items():
            if str(name).lower() != "python":
                add_package_candidate(
                    candidates,
                    str(name),
                    section="tool.poetry.dependencies",
                    source=rel,
                    version=str(version),
                )
        for group, group_data in (poetry.get("group", {}) or {}).items():
            for name, version in (group_data.get("dependencies", {}) or {}).items():
                add_package_candidate(
                    candidates,
                    str(name),
                    section="dev-dependencies",
                    source=f"{rel} [poetry.group.{group}]",
                    version=str(version),
                )

        for group, requirements in (data.get("dependency-groups", {}) or {}).items():
            for requirement in requirements or []:
                add_python_requirement(
                    candidates,
                    str(requirement),
                    section="dependency-groups",
                    source=f"{rel} [{group}]",
                )


def requirements_signals(root: Path, files: list[str], candidates: dict[str, Candidate]) -> None:
    for rel in files:
        name = Path(rel).name.lower()
        if not (name == "requirements.txt" or name.startswith("requirements-") and name.endswith(".txt")):
            continue
        add_candidate(
            candidates,
            "python-project",
            signal=f"{rel}: Python requirements file",
            priority=34,
            kind="ecosystem",
            display="Python project",
            research_terms={"requirements.txt", "Python packaging"},
        )
        for line in read_text(root / rel).splitlines():
            add_python_requirement(candidates, line, section="project.dependencies", source=rel)


def cargo_signals(root: Path, files: list[str], candidates: dict[str, Candidate]) -> None:
    for rel in files:
        if not rel.endswith("Cargo.toml"):
            continue
        data = read_toml(root / rel)
        add_candidate(
            candidates,
            "rust-cargo-project",
            signal=f"{rel}: Cargo manifest",
            priority=38,
            kind="ecosystem",
            display="Rust/Cargo project",
            research_terms={"Cargo.toml", "Rust crates"},
        )
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            for name, version in (data.get(section, {}) or {}).items():
                add_package_candidate(candidates, str(name), section=section, source=rel, version=str(version))


def go_mod_signals(root: Path, files: list[str], candidates: dict[str, Candidate]) -> None:
    for rel in files:
        if not rel.endswith("go.mod"):
            continue
        add_candidate(
            candidates,
            "go-module",
            signal=f"{rel}: Go module manifest",
            priority=38,
            kind="ecosystem",
            display="Go module",
            research_terms={"go.mod", "Go modules"},
        )
        in_require_block = False
        for raw_line in read_text(root / rel).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue
            if line == "require (":
                in_require_block = True
                continue
            if in_require_block and line == ")":
                in_require_block = False
                continue
            if line.startswith("require "):
                parts = line.split()
                if len(parts) >= 3:
                    add_package_candidate(candidates, parts[1], section="require", source=rel, version=parts[2])
                continue
            if in_require_block:
                parts = line.split()
                if len(parts) >= 2:
                    add_package_candidate(candidates, parts[0], section="require", source=rel, version=parts[1])


def composer_signals(root: Path, files: list[str], candidates: dict[str, Candidate]) -> None:
    for rel in files:
        if not rel.endswith("composer.json"):
            continue
        data = read_json(root / rel)
        add_candidate(
            candidates,
            "php-composer-project",
            signal=f"{rel}: Composer manifest",
            priority=36,
            kind="ecosystem",
            display="PHP/Composer project",
            research_terms={"composer.json", "PHP Composer"},
        )
        for section in ("require", "require-dev"):
            for name, version in (data.get(section, {}) or {}).items():
                if not str(name).startswith(("php", "ext-")):
                    add_package_candidate(candidates, str(name), section=section, source=rel, version=str(version))


def gemfile_signals(root: Path, files: list[str], candidates: dict[str, Candidate]) -> None:
    for rel in files:
        if Path(rel).name != "Gemfile":
            continue
        add_candidate(
            candidates,
            "ruby-bundler-project",
            signal=f"{rel}: Bundler manifest",
            priority=36,
            kind="ecosystem",
            display="Ruby/Bundler project",
            research_terms={"Gemfile", "Ruby Bundler"},
        )
        for line in read_text(root / rel).splitlines():
            match = re.match(r"\s*gem\s+['\"]([^'\"]+)['\"]", line)
            if match:
                add_package_candidate(candidates, match.group(1), section="dependencies", source=rel)


def config_topic(rel: str) -> tuple[str, str] | None:
    path = Path(rel)
    name = path.name
    lower = name.lower()
    rel_lower = rel.lower()

    if rel_lower.startswith(".github/workflows/") and lower.endswith((".yml", ".yaml")):
        return "github-actions", "GitHub Actions"
    if lower == "dockerfile" or lower.endswith(".dockerfile"):
        return "docker", "Docker"
    if lower in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
        return "docker-compose", "Docker Compose"

    rc_match = re.match(r"^\.([a-z0-9][a-z0-9_-]+)rc(?:\.[a-z0-9]+)?$", lower)
    if rc_match:
        topic = rc_match.group(1)
        return topic, pretty_display(topic)

    config_match = re.match(r"^([a-z0-9][a-z0-9_.-]*?)\.config(?:\.[a-z0-9]+)+$", lower)
    if config_match:
        topic = config_match.group(1).split(".", 1)[0]
        return topic, pretty_display(topic)

    if "/" not in rel and path.suffix.lower() in {".toml", ".yaml", ".yml", ".json"}:
        stem = path.stem.lower()
        if stem not in ROOT_CONFIG_EXCLUDES and not stem.endswith("-lock"):
            return stem, pretty_display(stem)

    if rel.count("/") <= 1 and path.suffix.lower() in {".toml", ".yaml", ".yml"}:
        stem = path.stem.lower()
        if stem not in ROOT_CONFIG_EXCLUDES:
            return stem, pretty_display(stem)

    return None


def config_signals(files: list[str], candidates: dict[str, Candidate], scripts: dict[str, str]) -> None:
    for rel in files:
        topic = config_topic(rel)
        if topic is None:
            continue
        raw_name, display = topic
        checks = matching_script_checks(scripts, {raw_name, display.lower()})
        priority = 58 if checks else 50
        add_candidate(
            candidates,
            raw_name,
            signal=f"{rel}: configuration file",
            priority=priority,
            kind="config",
            display=display,
            research_terms={display, raw_name},
            checks=checks,
        )


def language_signals(files: list[str], candidates: dict[str, Candidate]) -> None:
    counts: dict[str, tuple[str, int]] = {}
    for rel in files:
        suffix = Path(rel).suffix.lower()
        language = LANGUAGE_EXTENSIONS.get(suffix)
        if language is None:
            continue
        key, display = language
        _, count = counts.get(key, (display, 0))
        counts[key] = (display, count + 1)

    for key, (display, count) in counts.items():
        if count == 0:
            continue
        priority = 34 + min(count, 10)
        add_candidate(
            candidates,
            f"{key}-source",
            signal=f"{count} {display} source file(s)",
            priority=priority,
            kind="language",
            display=display,
            research_terms={display},
        )


def ecosystem_manifest_signals(files: list[str], candidates: dict[str, Candidate]) -> None:
    if any_file(set(files), "pom.xml", "*/pom.xml"):
        add_candidate(
            candidates,
            "java-maven-project",
            signal="pom.xml: Maven manifest",
            priority=36,
            kind="ecosystem",
            display="Java/Maven project",
            research_terms={"Maven", "pom.xml"},
        )
    if any_file(set(files), "build.gradle", "build.gradle.kts", "*/build.gradle", "*/build.gradle.kts"):
        add_candidate(
            candidates,
            "gradle-project",
            signal="Gradle build file",
            priority=36,
            kind="ecosystem",
            display="Gradle project",
            research_terms={"Gradle", "build.gradle"},
        )


def finalize_candidate(candidate: Candidate, default_checks: list[str]) -> dict[str, Any]:
    checks = sorted(candidate.checks) or default_checks or ["the closest existing test/lint/build command"]
    research_terms = sorted(candidate.research_terms or {candidate.display})
    research_queries = [
        f"{term} official documentation"
        for term in research_terms[:3]
    ]
    return {
        "id": candidate.key,
        "display": candidate.display,
        "skill_name": f"{candidate.key}-orchestrator",
        "priority": min(100, candidate.priority + min(20, len(candidate.signals) * 3)),
        "score": candidate.score,
        "kind": candidate.kind,
        "triggers": (
            f"{candidate.display} packages, plugins, config files, generated files, local usage patterns, "
            "build/runtime/test failures, integrations, or version-sensitive behavior"
        ),
        "docs": [],
        "research_queries": research_queries,
        "checks": checks,
        "signals": sorted(candidate.signals),
    }


def analyze_project(root: Path, max_files: int = 8000) -> dict[str, Any]:
    root = root.resolve()
    files = collect_files(root, max_files)
    file_set = set(files)
    candidates: dict[str, Candidate] = {}

    scripts = package_json_signals(root, files, candidates)
    pyproject_signals(root, files, candidates)
    requirements_signals(root, files, candidates)
    cargo_signals(root, files, candidates)
    go_mod_signals(root, files, candidates)
    composer_signals(root, files, candidates)
    gemfile_signals(root, files, candidates)
    ecosystem_manifest_signals(files, candidates)
    config_signals(files, candidates, scripts)
    language_signals(files, candidates)

    default_checks = validation_checks(scripts)
    detected_list = [finalize_candidate(candidate, default_checks) for candidate in candidates.values()]
    detected_list.sort(key=lambda item: (-int(item["priority"]), -int(item["score"]), str(item["display"])))
    for item in detected_list:
        item.pop("score", None)

    package_managers = []
    for marker, name in PACKAGE_MANAGER_MARKERS:
        if marker in file_set:
            package_managers.append(name)

    return {
        "project_root": str(root),
        "file_count_scanned": len(files),
        "package_managers": sorted(set(package_managers)),
        "package_scripts": scripts,
        "detected": detected_list,
    }


def print_human(report: dict[str, Any]) -> None:
    print(f"Project: {report['project_root']}")
    managers = ", ".join(report["package_managers"]) or "none detected"
    print(f"Package managers: {managers}")
    print("Detected stack:")
    if not report["detected"]:
        print("- none")
        return
    for item in report["detected"]:
        signals = "; ".join(item["signals"])
        kind = item.get("kind", "stack")
        print(f"- {item['display']} -> {item['skill_name']} [{kind}] ({signals})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="Project root to analyze")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a human summary")
    parser.add_argument("--max-files", type=int, default=8000, help="Maximum files to scan")
    args = parser.parse_args()

    report = analyze_project(Path(args.project), max_files=args.max_files)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
