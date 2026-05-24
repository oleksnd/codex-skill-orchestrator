from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill-orchestrator" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analyze_project import analyze_project  # noqa: E402
from bootstrap_project import MANAGED_MARKER, bootstrap  # noqa: E402


class SkillOrchestratorTests(unittest.TestCase):
    def test_analyzer_detects_package_manager_from_package_json_and_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text(
                json.dumps(
                    {
                        "packageManager": "pnpm@9.12.0",
                        "scripts": {
                            "build": "vite build",
                            "lint": "eslint .",
                        },
                        "dependencies": {
                            "react": "^19.0.0",
                        },
                        "devDependencies": {
                            "vite": "^6.0.0",
                            "typescript": "^5.8.0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (project / "pnpm-workspace.yaml").write_text("packages:\n  - packages/*\n", encoding="utf-8")
            (project / "src").mkdir()
            (project / "src" / "App.tsx").write_text("export function App() { return null; }\n", encoding="utf-8")

            report = analyze_project(project)
            ids = {item["id"] for item in report["detected"]}

            self.assertIn("pnpm", report["package_managers"])
            self.assertIn("javascript-node-project", ids)
            self.assertIn("react", ids)
            self.assertIn("vite", ids)
            self.assertIn("typescript", ids)
            self.assertEqual(report["package_scripts"]["build"], "vite build")
            self.assertEqual(report["diagnostics"], [])

    def test_analyzer_reports_manifest_diagnostics_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text('{"scripts":', encoding="utf-8")
            (project / "pyproject.toml").write_text("[project\n", encoding="utf-8")

            report = analyze_project(project)
            diagnostics = "\n".join(report["diagnostics"])
            ids = {item["id"] for item in report["detected"]}

            self.assertIn("package.json: invalid JSON", diagnostics)
            self.assertIn("pyproject.toml: invalid TOML", diagnostics)
            self.assertIn("javascript-node-project", ids)
            self.assertIn("python-project", ids)

    def test_analyzer_reports_max_file_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "a.py").write_text("print('a')\n", encoding="utf-8")
            (project / "b.py").write_text("print('b')\n", encoding="utf-8")

            report = analyze_project(project, max_files=1)

            self.assertEqual(report["file_count_scanned"], 1)
            self.assertIn("file scan reached --max-files=1", "\n".join(report["diagnostics"]))

    def test_bootstrap_removes_stale_managed_skill_but_keeps_custom_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^19.0.0"}}),
                encoding="utf-8",
            )

            stale = project / ".codex" / "skills" / "old-orchestrator" / "SKILL.md"
            stale.parent.mkdir(parents=True)
            stale.write_text(f"---\nname: old-orchestrator\n---\n\n{MANAGED_MARKER}\n", encoding="utf-8")

            custom = project / ".codex" / "skills" / "custom-orchestrator" / "SKILL.md"
            custom.parent.mkdir(parents=True)
            custom.write_text("---\nname: custom-orchestrator\n---\n\n# Custom\n", encoding="utf-8")

            result = bootstrap(project, dry_run=False, max_stack_skills=3, local_dir=".codex")
            manifest = json.loads((project / ".codex" / "skill-orchestrator" / "manifest.json").read_text())

            self.assertFalse(stale.exists())
            self.assertTrue(custom.exists())
            self.assertIn("react-orchestrator", manifest["generated_skills"])
            self.assertNotIn("old-orchestrator", manifest["generated_skills"])
            self.assertTrue(any(change.startswith("remove stale managed skill") for change in result["changes"]))

    def test_bootstrap_dry_run_reports_stale_cleanup_without_removing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^19.0.0"}}),
                encoding="utf-8",
            )
            stale = project / ".codex" / "skills" / "old-orchestrator" / "SKILL.md"
            stale.parent.mkdir(parents=True)
            stale.write_text(f"---\nname: old-orchestrator\n---\n\n{MANAGED_MARKER}\n", encoding="utf-8")

            result = bootstrap(project, dry_run=True, max_stack_skills=3, local_dir=".codex")

            self.assertTrue(stale.exists())
            self.assertTrue(any(change.startswith("remove stale managed skill") for change in result["changes"]))


if __name__ == "__main__":
    unittest.main()
