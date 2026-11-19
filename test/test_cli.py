"""CLI contract tests, including the standalone entry point."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "skill-lineage.py"
BODY = "A short body for this skill."


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + [str(arg) for arg in args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def write_skill(base, rel, name, description, body=BODY):
    path = base / rel / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "---\nname: %s\ndescription: %s\n---\n\n%s\n" % (name, description, body)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scan_json_clean(self):
        write_skill(self.root, "a", "alpha", "First alpha skill.")
        result = run("scan", self.root, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["tool"], "skill-lineage")
        self.assertEqual(payload["command"], "scan")
        self.assertEqual(payload["analysis"]["summary"]["skills"], 1)
        self.assertEqual(payload["exit_code"], 0)

    def test_scan_fail_on_any(self):
        write_skill(self.root, "a", "alpha", "First alpha skill.")
        write_skill(self.root, "b", "alpha", "First alpha skill.")
        result = run("scan", self.root, "--json", "--fail-on", "any")
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["analysis"]["summary"]["exact_copies"], 1)
        self.assertEqual(payload["exit_code"], 1)

    def test_fail_on_conflict_ignores_exact_copies(self):
        write_skill(self.root, "a", "alpha", "First alpha skill.")
        write_skill(self.root, "b", "alpha", "First alpha skill.")
        result = run("scan", self.root, "--json", "--fail-on", "conflict")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fail_on_conflict_detects_collision(self):
        write_skill(
            self.root,
            "a",
            "browser",
            "Automate a headless browser for QA.",
            "Clicks buttons and fills forms in web pages and reports console errors.",
        )
        write_skill(
            self.root,
            "b",
            "browser",
            "Browse a local file tree in the terminal.",
            "Lists directories, filters glob patterns and prints sizes on disk.",
        )
        result = run("scan", self.root, "--json", "--fail-on", "conflict")
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["analysis"]["summary"]["name_conflicts"], 1)

    def test_plan_json(self):
        write_skill(self.root, "a", "alpha", "First alpha skill.")
        write_skill(self.root, "b", "alpha", "First alpha skill.")
        result = run("plan", self.root, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["plan"]["dry_run"])
        self.assertFalse(payload["plan"]["destructive"])
        action = payload["plan"]["actions"][0]
        self.assertEqual(action["action"], "remove-candidate")
        self.assertIn("duplicate_of", action)

    def test_plan_text(self):
        write_skill(self.root, "a", "alpha", "First alpha skill.")
        result = run("plan", self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry run: True", result.stdout)
        self.assertIn("No cleanup candidates found.", result.stdout)

    def test_report_markdown(self):
        write_skill(self.root, "a", "alpha", "First alpha skill.")
        result = run("report", self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Summary", result.stdout)
        self.assertIn("## Exact duplicates", result.stdout)

    def test_near_threshold_validation(self):
        write_skill(self.root, "a", "alpha", "First alpha skill.")
        result = run("scan", self.root, "--near", "2")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--near", result.stderr)

    def test_empty_catalog_is_tool_error(self):
        result = run("scan", self.root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no SKILL.md", result.stderr)

    def test_missing_command_prints_help(self):
        result = run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stdout)

    def test_module_entry_point(self):
        result = subprocess.run(
            [sys.executable, "-m", "skill_lineage", "scan", ".", "--json"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["command"], "scan")


if __name__ == "__main__":
    unittest.main()
