import tempfile
from pathlib import Path
import json
import unittest
import re
from build_knowledge_navigation import build


import importlib.util

spec = importlib.util.spec_from_file_location(
    "validator",
    Path(__file__).resolve().parent.parent / "scripts/validate-knowledge-wiki.py",
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
metadata = validator.frontmatter


class NavigationTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)

    def page(self, name, title="Client", kind="project"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntype: "
            + kind
            + "\ntitle: "
            + title
            + "\nstatus_evidence_date: 2026-10-26\n---\n\n## Current status — 2026-10-26\n\n- Repository access is missing.\n"
        )

    def test_stale_duplicate_root_is_replaced_by_canonical_navigation(self):
        self.page("projects/client.md")
        (self.root / "index.md").write_text(
            "[Client](projects/client.md)\n[Client again](projects/client.md)\nHistorical backfill audit\n"
        )
        (self.root / "ingestion.json").write_text(
            json.dumps({"files": {"source": {"modifiedTime": "2026-10-26T12:00:00Z"}}})
        )
        build(self.root, "timeless", metadata)
        root = (self.root / "index.md").read_text()
        self.assertEqual(root.count("(projects/client.md)"), 1)
        self.assertNotIn("Historical backfill", root)
        self.assertIn("2026-10-26", root)
        self.assertFalse(build(self.root, "timeless", metadata))

    def test_historical_source_titles_stay_behind_evidence_navigation(self):
        self.page("topics/historical-weekly.md", "Private weekly title", "topic")
        build(self.root, "timeless", metadata)
        self.assertNotIn("Private weekly title", (self.root / "index.md").read_text())
        self.assertIn(
            "Private weekly title", (self.root / "topics/evidence-index.md").read_text()
        )
        self.assertNotIn(
            "historical-weekly", (self.root / "topics/index.md").read_text()
        )

    def test_alias_redirect_does_not_create_a_second_project(self):
        self.page("projects/client.md")
        self.page("projects/legacy.md", "Legacy spelling", "redirect")
        build(self.root, "timeless", metadata)
        self.assertNotIn("legacy.md", (self.root / "projects/index.md").read_text())


if __name__ == "__main__":
    unittest.main()
