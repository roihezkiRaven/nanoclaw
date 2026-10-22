"""Regression checks for knowledge isolation and metadata validation."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("validator", Path(__file__).with_name("validate-knowledge-wiki.py"))
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
META = "---\ntype: topic\ntitle: Page\ndescription: Evidence\ntags: []\ngenerated: 2026-10-22\nsources: []\n---\n"


class KnowledgeValidationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "wiki"
        self.root.mkdir()

    def page(self, name, text=META):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_whatsapp_brain_requires_frontmatter(self):
        self.page("whatsapp/brain/overview.md", "# Missing metadata")
        self.assertTrue(any("missing frontmatter" in e for e in validator.validate(self.root)))

    def test_nested_metadata_cannot_replace_top_level_fields(self):
        self.assertNotIn("title", validator.frontmatter("---\nsources:\n  title: nested\n---\n"))

    def test_both_brains_enforce_resolved_isolation(self):
        self.page("brain/overview.md", META + "[other](../whatsapp/brain/overview.md)")
        self.page("whatsapp/brain/overview.md", META + "[other](../../brain/overview.md)")
        self.assertEqual(sum("isolation boundary" in e for e in validator.validate(self.root)), 2)

    def test_existing_file_outside_wiki_is_rejected(self):
        (self.root.parent / "outside.md").write_text("external")
        self.page("topics/page.md", META + "[external](../../outside.md)")
        self.assertTrue(any("escapes knowledge wiki" in e for e in validator.validate(self.root)))

    def test_checkpoint_requires_source_map(self):
        (self.root / "ingestion.json").write_text("[]")
        self.assertTrue(any("invalid checkpoint" in e for e in validator.validate(self.root)))

    def test_weekly_links_resolve_from_the_weekly_directory(self):
        self.page("whatsapp/brain/weekly/week.md", META + "[digest](../group/day.md)")
        self.page("whatsapp/group/day.md", META.replace("sources: []", "sources: []\ngroup_label: Group\ngroup_jid: group"))
        errors = validator.validate(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("broken link", errors[0])

    def test_valid_graph_and_legacy_checkpoint_pass(self):
        self.page("brain/overview.md", META + "[topic](../topics/page.md)")
        self.page("topics/page.md")
        self.page("whatsapp/brain/overview.md")
        (self.root / "ingestion.json").write_text('{"files": {"source": {"modifiedTime": "2026-10-22T00:00:00Z"}}}')
        self.assertEqual(validator.validate(self.root), [])

    def test_unsourced_cross_group_placeholder_is_not_a_daily_digest(self):
        text = META.replace("type: topic", "type: digest").replace("sources: []", "sources: []\ngroup_label: Group\ngroup_jid: cross-group")
        self.page("whatsapp/group/2026-10-22.md", text)
        errors = validator.validate(self.root)
        self.assertTrue(any("exact group JID" in e for e in errors))
        self.assertTrue(any("no source provenance" in e for e in errors))
        self.page("whatsapp/group/2026-10-22.md", text.replace("type: digest", "type: coverage-status"))
        self.assertEqual(validator.validate(self.root), [])

    def test_raw_chat_and_sender_identifiers_are_not_learning_digests(self):
        self.page("whatsapp/brain/overview.md", META + "- [2026-10-22T10:00:00Z] raw message\nsender_jid: private\n")
        errors = validator.validate(self.root)
        self.assertTrue(any("copied timestamped" in e for e in errors))
        self.assertTrue(any("sender identifier" in e for e in errors))

    def project_checkpoint(self, outputs):
        item = {"modifiedTime": "2026-10-22T10:00:00Z", "outputs": outputs, "project_outputs": outputs}
        (self.root / "ingestion.json").write_text(json.dumps({"files": {"source": item}}))

    def test_project_checkpoint_requires_a_canonical_project_not_an_archive(self):
        self.page("topics/archive.md", META.replace("sources: []", "sources: []") + "source")
        self.project_checkpoint(["topics/archive.md"])
        self.assertTrue(any("canonical project page" in e for e in validator.validate(self.root)))

    def test_project_checkpoint_requires_exact_revision_not_just_a_source_mention(self):
        self.page("projects/client.md", META.replace("type: topic", "type: project") + "source")
        self.project_checkpoint(["projects/client.md"])
        self.assertTrue(any("exact source ID" in e for e in validator.validate(self.root)))
        source = "sources:\n  - id: source\n    modified: 2026-10-21T10:00:00Z"
        self.page("projects/client.md", META.replace("type: topic", "type: project").replace("sources: []", source))
        self.assertTrue(any("observed modification time" in e for e in validator.validate(self.root)))

    def test_project_checkpoint_accepts_current_cited_project(self):
        source = "sources:\n  - id: source\n    modified: 2026-10-22T10:00:00Z"
        self.page("projects/client.md", META.replace("type: topic", "type: project").replace("sources: []", source))
        self.project_checkpoint(["projects/client.md"])
        self.assertEqual(validator.validate(self.root), [])

    def test_project_checkpoint_rejects_malformed_lists(self):
        self.project_checkpoint("projects/client.md")
        self.assertTrue(any("project_outputs must be a list" in e for e in validator.validate(self.root)))


if __name__ == "__main__":
    unittest.main()
