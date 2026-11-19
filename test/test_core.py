"""Core behavior tests: discovery, fingerprints, grouping and planning."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skill_lineage.discover import discover, root_label
from skill_lineage.fingerprint import fingerprint, jaccard
from skill_lineage.group import analyze, build_plan
from skill_lineage.report import render_markdown

BODY = "A short body for this skill."


def write_skill(base, rel, name, description, body=BODY):
    path = base / rel / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "---\nname: %s\ndescription: %s\n---\n\n%s\n" % (name, description, body)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def write_text(base, rel, text):
    path = base / rel / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def analyze_paths(paths, near=0.85):
    records = discover([str(path) for path in paths])
    prints = [fingerprint(record.raw, record.doc) for record in records]
    return analyze(records, prints, near_threshold=near)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_exact_duplicates(self):
        first = write_skill(self.root, "a", "alpha", "First alpha skill.")
        second = write_skill(self.root, "b", "alpha", "First alpha skill.")
        result = analyze_paths([first, second])
        summary = result["summary"]
        self.assertEqual(summary["skills"], 2)
        self.assertEqual(summary["exact_groups"], 1)
        self.assertEqual(summary["exact_copies"], 1)
        self.assertEqual(summary["normalized_groups"], 0)
        self.assertEqual(summary["name_conflicts"], 0)
        self.assertEqual(summary["name_variants"], 0)

    def test_normalized_duplicate_with_reordered_frontmatter(self):
        first = write_skill(self.root, "a", "alpha", "First alpha skill.")
        second = write_text(
            self.root,
            "b",
            "---\ndescription: First alpha skill.\nname: alpha\n---\n\n"
            + BODY
            + "\n",
        )
        records = discover([str(first), str(second)])
        prints = [fingerprint(record.raw, record.doc) for record in records]
        self.assertNotEqual(prints[0].exact, prints[1].exact)
        self.assertEqual(prints[0].normalized, prints[1].normalized)
        result = analyze(records, prints)
        self.assertEqual(result["summary"]["exact_groups"], 0)
        self.assertEqual(result["summary"]["normalized_groups"], 1)
        self.assertEqual(result["summary"]["normalized_copies"], 1)

    def test_jaccard(self):
        self.assertEqual(jaccard(frozenset(), frozenset()), 1.0)
        left = frozenset(["alpha", "beta", "gamma"])
        right = frozenset(["beta", "gamma", "delta"])
        self.assertAlmostEqual(jaccard(left, right), 0.5)
        self.assertEqual(jaccard(left, left), 1.0)

    def test_name_conflict(self):
        first = write_skill(
            self.root,
            "a",
            "browser",
            "Automate a headless browser for QA.",
            "Clicks buttons and fills forms in web pages and reports console errors.",
        )
        second = write_skill(
            self.root,
            "b",
            "browser",
            "Browse a local file tree in the terminal.",
            "Lists directories, filters glob patterns and prints sizes on disk.",
        )
        result = analyze_paths([first, second])
        self.assertEqual(result["summary"]["name_conflicts"], 1)
        self.assertEqual(result["summary"]["name_variants"], 0)
        self.assertEqual(len(result["conflicts"][0]["candidates"]), 1)

    def test_name_variant(self):
        first = write_skill(
            self.root,
            "a",
            "browser",
            "Automate a headless browser for QA. Uses Playwright.",
        )
        second = write_skill(
            self.root,
            "b",
            "browser",
            "Automate a headless browser for QA. Uses Puppeteer.",
        )
        result = analyze_paths([first, second])
        self.assertEqual(result["summary"]["name_variants"], 1)
        self.assertEqual(result["summary"]["name_conflicts"], 0)

    def test_cjk_translation_is_not_exact(self):
        first = write_skill(self.root, "en", "browser", "Automate a headless browser.")
        second = write_skill(
            self.root,
            "zh",
            "browser",
            "Automate a headless browser.",
            "此技能会自动操作浏览器并报告错误。",
        )
        records = discover([str(first), str(second)])
        self.assertFalse(records[0].translated)
        self.assertTrue(records[1].translated)
        result = analyze(records, [fingerprint(r.raw, r.doc) for r in records])
        self.assertEqual(result["summary"]["exact_groups"], 0)
        self.assertGreater(result["summary"]["remove_candidates"], 0)
        group = (result["variants"] + result["conflicts"])[0]
        self.assertLess(
            result["summary"]["remove_candidates"],
            5,
            "translated copy should be one candidate, not a full split",
        )
        self.assertTrue(group["candidates"])

    def test_canonical_prefers_complete_frontmatter(self):
        weak = write_skill(
            self.root,
            "a",
            "alpha",
            "x",
            "Completely different words about fishing rods and rivers.",
        )
        strong = write_skill(
            self.root,
            "b",
            "alpha",
            "A descriptive name for this skill used by the catalog tests.",
            "Unrelated prose about satellites orbiting a distant planet.",
        )
        result = analyze_paths([weak, strong])
        group = (result["conflicts"] + result["variants"])[0]
        self.assertEqual(group["canonical"], strong.parent.as_posix())
        self.assertIn("complete frontmatter", group["canonical_reason"])

    def test_plan_is_review_only(self):
        first = write_skill(self.root, "a", "alpha", "First alpha skill.")
        second = write_skill(self.root, "b", "alpha", "First alpha skill.")
        plan = build_plan(analyze_paths([first, second]))
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["destructive"])
        self.assertEqual(len(plan["actions"]), 1)
        action = plan["actions"][0]
        self.assertEqual(action["action"], "remove-candidate")
        self.assertEqual(action["confidence"], "exact")
        self.assertFalse(action["requires_review"])
        self.assertEqual(action["duplicate_of"], first.parent.as_posix())

    def test_non_exact_candidates_require_review(self):
        first = write_skill(self.root, "a", "alpha", "First alpha skill.")
        second = write_skill(self.root, "b", "alpha", "Second alpha skill, rewritten.")
        plan = build_plan(analyze_paths([first, second]))
        self.assertTrue(plan["actions"])
        self.assertTrue(all(item["requires_review"] for item in plan["actions"]))

    def test_report_renders_summary(self):
        first = write_skill(self.root, "a", "alpha", "First alpha skill.")
        second = write_skill(self.root, "b", "alpha", "First alpha skill.")
        markdown = render_markdown(analyze_paths([first, second]), [str(self.root)])
        self.assertIn("# skill-lineage report", markdown)
        self.assertIn("| Exact copies | 1 |", markdown)
        self.assertIn("Candidate:", markdown)
        self.assertIn("never deletes files", markdown)

    def test_discover_skips_dependencies_and_dedupes(self):
        wanted = write_skill(self.root, "a", "one", "First skill here.")
        write_skill(self.root, "node_modules/pkg", "junk", "Junk skill here.")
        write_skill(self.root, "__pycache__/pkg", "junk", "Junk skill too.")
        records = discover([str(self.root), str(wanted)])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, "one")

    def test_root_label_classification(self):
        self.assertEqual(root_label("/x/local-skills/a"), "local")
        self.assertEqual(root_label("/x/.claude/skills/a"), "claude")
        self.assertEqual(root_label("/x/vendor/pkg/a"), "vendor")
        self.assertEqual(root_label("/tmp/custom/a"), "custom")


if __name__ == "__main__":
    unittest.main()
