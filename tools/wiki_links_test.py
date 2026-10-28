import tempfile
from pathlib import Path
import unittest
from wiki_links import exported_text, readable_markdown


class WikiLinkTests(unittest.TestCase):
    def test_nested_backlinks_use_stable_drive_ids(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "brain/concepts/a.md"
            p.parent.mkdir(parents=True)
            p.write_text(
                "[project](../../projects/client.md#status) [same](#top) [web](https://example.com/a)"
            )
            output = exported_text(p, root, {"projects/client.md": "published_id"})
            self.assertEqual(
                output,
                "[project](https://drive.google.com/file/d/published_id/view) [same](#top) [web](https://example.com/a)",
            )
            self.assertIn("../../projects", p.read_text())

    def test_missing_identity_cannot_publish_broken_navigation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "index.md"
            p.write_text("[missing](missing.md)")
            with self.assertRaisesRegex(ValueError, "no published page"):
                exported_text(p, root, {})

    def test_escaping_knowledge_scope_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "index.md"
            p.write_text("[private](../private.md)")
            with self.assertRaisesRegex(ValueError, "escapes"):
                exported_text(p, root, {})

    def test_reader_export_hides_frontmatter_and_retains_explicit_evidence(self):
        text = "---\ntype: project\nstatus_evidence_date: 2026-10-26\nsources:\n  - id: original\n    url: https://example.com/source\n---\n\n# Project\n\nA dated fact.\n"
        output = readable_markdown(text)
        self.assertTrue(output.startswith("# Project"))
        self.assertNotIn("type: project", output)
        self.assertIn("Evidence through: 2026-10-26", output)
        self.assertIn("[Source](https://example.com/source)", output)

    def test_canonical_input_and_bare_source_ids_are_not_reinterpreted(self):
        text = (
            "---\ntype: reference\nsources: [owner-confirmation]\n---\n\n# Reference\n"
        )
        self.assertNotIn("drive.google", readable_markdown(text))


if __name__ == "__main__":
    unittest.main()
