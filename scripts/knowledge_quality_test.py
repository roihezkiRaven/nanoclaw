"""Regression checks for the consolidation defects seen in the live wiki."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "quality", Path(__file__).with_name("knowledge_quality.py")
)
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


class QualityTests(unittest.TestCase):
    def test_only_one_current_status_is_allowed(self):
        meta = {"type": "project", "status_evidence_date": "2026-10-26"}
        self.assertTrue(
            quality.project_errors(
                "projects/client.md",
                "## Current status — 2026-10-22\n\n## Current status — 2026-10-26",
                meta,
            )
        )
        self.assertFalse(
            quality.project_errors(
                "projects/client.md",
                "## Current status — 2026-10-26\n\n### Prior assessment — 2026-10-22",
                meta,
            )
        )

    def test_new_metadata_cannot_hide_old_current_heading(self):
        self.assertTrue(
            quality.project_errors(
                "projects/client.md",
                "## Current status — 2026-10-22",
                {"type": "project", "status_evidence_date": "2026-10-26"},
            )
        )

    def test_aliases_resolve_to_one_project(self):
        pages = [
            (
                "projects/a.md",
                "",
                {"type": "project", "aliases": '["Client", "Old spelling"]'},
            ),
            ("projects/b.md", "", {"type": "project", "aliases": '["old SPELLING"]'}),
        ]
        self.assertEqual(len(quality.alias_errors(pages)), 1)
        pages[1][2]["type"] = "redirect"
        self.assertFalse(quality.alias_errors(pages))

    def test_duplicate_navigation_and_fragments_are_rejected(self):
        self.assertTrue(
            quality.navigation_errors(
                Path("index.md"), "[a](projects/a.md) [b](projects/a.md#new)"
            )
        )

    def test_project_assessment_must_include_source_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "projects").mkdir()
            (root / "projects/a.md").write_text("page")
            a = {
                "project": "projects/a.md",
                "outcome": "updated",
                "reason": "source-specific fact",
            }
            errors = quality.assessment_errors(
                root, "source", {"project_assessments": [a]}
            )
            self.assertEqual(len(errors), 2)
            a["evidence"] = "original source section"
            self.assertFalse(
                quality.assessment_errors(
                    root,
                    "source",
                    {"project_outputs": ["projects/a.md"], "project_assessments": [a]},
                )
            )

    def test_malformed_assessment_and_traversal_fail_closed(self):
        self.assertTrue(
            quality.assessment_errors(
                Path("/wiki"), "s", {"project_assessments": ["wrong"]}
            )
        )
        self.assertTrue(
            quality.assessment_errors(
                Path("/wiki"),
                "s",
                {"project_assessments": [{"project": "projects/../../private.md"}]},
            )
        )

    def test_concept_is_more_than_a_log_or_links(self):
        self.assertTrue(
            quality.concept_errors(
                "brain/concepts/a.md",
                "# New daily mention",
                {"type": "concept", "sources": "[]"},
            )
        )

    def test_known_project_mentions_cannot_be_checkpointed_without_assessment(self):
        import json

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "projects").mkdir()
            (root / "projects/client.md").write_text("client")
            meta = lambda text: {"type": "project", "aliases": '["Example Client"]'}
            source = {
                "complete": True,
                "meta": {"modifiedTime": "revision"},
                "text": "Delivery: Example Client lacks repository access.",
            }
            item = {"modifiedTime": "revision", "project_assessments": []}
            self.assertTrue(
                quality.source_review_errors(root, "source", item, source, meta)
            )
            item["project_assessments"] = [
                {"project": "projects/client.md", "evidence": "lacks repository access"}
            ]
            self.assertFalse(
                quality.source_review_errors(root, "source", item, source, meta)
            )
            item["project_assessments"][0]["evidence"] = "access is fixed"
            self.assertTrue(
                quality.source_review_errors(root, "source", item, source, meta)
            )

    def test_source_review_requires_same_complete_revision(self):
        self.assertTrue(
            quality.source_review_errors(
                Path("/wiki"),
                "source",
                {"modifiedTime": "new"},
                {"complete": True, "meta": {"modifiedTime": "old"}},
                lambda text: {},
            )
        )

    def test_case_sensitive_alias_avoids_common_word_collision(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "projects").mkdir()
            (root / "projects/client.md").write_text("client")
            meta = lambda text: {
                "type": "project",
                "aliases": '["Example"]',
                "case_sensitive_aliases": '["Example"]',
            }
            self.assertFalse(
                quality.mentioned_projects(root, "an example of a workflow", meta)
            )
            self.assertTrue(
                quality.mentioned_projects(root, "Example has a new milestone", meta)
            )

    def test_citation_in_metadata_cannot_substitute_for_a_consolidated_fact(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "projects").mkdir()
            p = root / "projects/client.md"
            assessment = {
                "project": "projects/client.md",
                "outcome": "updated",
                "reason": "Repository access remains blocked.",
            }
            p.write_text("---\nsources: [source-id]\n---\n# Client\nNothing updated.")
            self.assertTrue(quality.updated_claim_errors(root, "source-id", assessment))
            p.write_text(
                "---\nsources: [source-id]\n---\n- Repository access remains blocked."
            )
            self.assertTrue(quality.updated_claim_errors(root, "source-id", assessment))
            p.write_text(
                "---\nsources: []\n---\n- Repository access remains blocked. [source](https://example.com/source-id)"
            )
            self.assertFalse(
                quality.updated_claim_errors(root, "source-id", assessment)
            )

    def test_blanket_ambiguity_is_rejected_even_with_real_excerpt(self):
        assessment = {
            "project": "projects/client.md",
            "outcome": "unresolved",
            "reason": "Legacy consolidation review: mentioned in contextual material.",
            "uncertainty": "unknown",
        }
        self.assertTrue(
            quality.disposition_errors(Path("/wiki"), "source", assessment, set())
        )

    def test_explicit_project_cannot_be_excluded_or_left_ambiguous(self):
        for outcome, field in [
            ("no_material_change", "scope_exclusion"),
            ("unresolved", "uncertainty"),
        ]:
            assessment = {
                "project": "projects/client.md",
                "outcome": outcome,
                "reason": "specific",
                field: "specific explanation",
            }
            self.assertTrue(
                quality.disposition_errors(
                    Path("/wiki"), "source", assessment, {"projects/client.md"}
                )
            )
            self.assertFalse(
                quality.disposition_errors(Path("/wiki"), "source", assessment, set())
            )

    def test_no_change_requires_an_existing_retained_fact(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "projects").mkdir()
            (root / "projects/client.md").write_text(
                "---\nsources: []\n---\nAccess remains blocked."
            )
            a = {
                "project": "projects/client.md",
                "outcome": "no_material_change",
                "reason": "already captured",
                "retained_fact": "Access is available.",
            }
            self.assertTrue(quality.disposition_errors(root, "source", a, set()))
            a["retained_fact"] = "Access remains blocked."
            self.assertFalse(
                quality.disposition_errors(root, "source", a, {"projects/client.md"})
            )

    def test_concise_canonical_fact_allows_consolidation_without_log_prose(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'projects').mkdir()
            (root/'projects/a.md').write_text('---\nsources: []\n---\nAccess remains blocked. [source](https://example.com/source-id)')
            a={'project':'projects/a.md','outcome':'updated','reason':'Detailed source assessment kept in checkpoint.', 'canonical_fact':'Access remains blocked.'}
            self.assertFalse(quality.updated_claim_errors(root,'source-id',a))
            a['canonical_fact']='Access is working.'
            self.assertTrue(quality.updated_claim_errors(root,'source-id',a))


if __name__ == "__main__":
    unittest.main()
