"""Publication safety and recovery tests, with no external services."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).with_name('publish_knowledge_wiki.py'))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
META = '---\ntype: topic\ntitle: Page\ndescription: Evidence\ntags: []\ngenerated: 2026-10-24\nsources: []\n---\n'
DAILY = META.replace('sources: []', 'sources: [evidence]\ngroup_label: Group\ngroup_jid: "123456789@g.us"')
WEEKLY = META.replace('type: topic', 'type: whatsapp-weekly')


class PublicationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'wiki'
        self.root.mkdir()
        self.state = self.root.parent / 'state'
        self.uploads = []
        self.page('whatsapp/brain/overview.md', META)
        self.page('whatsapp/group/2026-10-23.md', DAILY)

    def page(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def upload(self, stage):
        self.assertEqual(publisher.validator.validate(stage, 'whatsapp'), [])
        self.uploads.append({p.relative_to(stage).as_posix(): p.read_text() for p in stage.rglob('*.md')})

    def publish(self, upload=None):
        return publisher.publish(self.root, self.state, 'whatsapp', upload or self.upload)

    def test_snapshot_is_scoped_and_excludes_secrets(self):
        self.page('brain/private.md', 'not part of WhatsApp')
        self.page('whatsapp/.env', 'secret')
        self.assertEqual(self.publish()['mode'], 'healthy')
        self.assertEqual(len(self.uploads[0]), 2)
        self.assertTrue((self.state / 'last-good.zip').is_file())

    def test_repairs_both_body_and_source_paths_and_is_idempotent(self):
        text = WEEKLY.replace('sources: []', 'sources: ["../group/2026-10-23.md"]') + '[digest](../group/2026-10-23.md)'
        page = self.page('whatsapp/brain/weekly/2026-10-24.md', text)
        status = self.publish()
        self.assertEqual(status['mode'], 'repaired')
        self.assertEqual(len(status['repairs']), 2)
        self.assertEqual(page.read_text().count('../../group/2026-10-23.md'), 2)
        self.assertEqual((self.state / 'repair-originals/whatsapp/brain/weekly/2026-10-24.md').read_text(), text)
        self.assertEqual(self.publish()['mode'], 'healthy')

    def test_fallback_keeps_fresh_daily_pages_and_old_synthesis(self):
        first = self.publish()
        self.page('whatsapp/brain/overview.md', 'malformed synthesis')
        self.page('whatsapp/group/2026-10-24.md', DAILY + 'Fresh evidence')
        status = self.publish()
        self.assertEqual(status['mode'], 'degraded')
        self.assertEqual(status['brain_snapshot_at'], first['brain_snapshot_at'])
        self.assertEqual(self.uploads[-1]['whatsapp/brain/overview.md'], META)
        self.assertIn('Fresh evidence', self.uploads[-1]['whatsapp/group/2026-10-24.md'])
        self.assertTrue((self.state / 'rejected.zip').exists())
        self.assertEqual((self.root / 'whatsapp/brain/overview.md').read_text(), 'malformed synthesis')

    def test_timeless_fallback_is_independent_of_whatsapp(self):
        self.page('brain/overview.md', META)
        self.page('topics/source.md', META)
        state = self.root.parent / 'timeless-state'
        uploads = []
        def upload(stage):
            self.assertFalse((stage / 'whatsapp').exists())
            self.assertEqual(publisher.validator.validate(stage, 'timeless'), [])
            uploads.append((stage / 'brain/overview.md').read_text())
        publisher.publish(self.root, state, 'timeless', upload)
        self.page('brain/overview.md', 'bad synthesis')
        status = publisher.publish(self.root, state, 'timeless', upload)
        self.assertEqual(status['mode'], 'degraded')
        self.assertEqual(uploads, [META, META])

    def test_root_navigation_is_restored_with_fallback(self):
        self.page('whatsapp/index.md', DAILY + '[brain](brain/overview.md)')
        self.publish()
        self.page('whatsapp/index.md', DAILY + '[bad](brain/weekly/missing.md)')
        self.page('whatsapp/brain/overview.md', 'bad synthesis')
        self.assertEqual(self.publish()['mode'], 'degraded')
        self.assertNotIn('missing.md', self.uploads[-1]['whatsapp/index.md'])

    def test_invalid_daily_cannot_be_hidden_by_fallback(self):
        self.publish()
        self.page('whatsapp/group/2026-10-24.md', DAILY.replace('123456789@g.us', 'unknown'))
        with self.assertRaisesRegex(ValueError, 'Fallback cannot'):
            self.publish()
        self.assertEqual(len(self.uploads), 1)

    def test_invalid_first_run_fails_closed(self):
        self.page('whatsapp/brain/overview.md', 'bad')
        with self.assertRaisesRegex(ValueError, 'no last-good'):
            self.publish()
        self.assertEqual(self.uploads, [])

    def test_upload_failure_preserves_cache_and_source(self):
        self.publish()
        previous = (self.state / 'last-good.zip').read_bytes()
        page = self.page('whatsapp/brain/weekly/2026-10-24.md', WEEKLY + '[daily](../group/2026-10-23.md)')
        def fail(stage):
            raise RuntimeError('transient upload failure')
        with self.assertRaises(RuntimeError):
            self.publish(fail)
        self.assertEqual((self.state / 'last-good.zip').read_bytes(), previous)
        self.assertIn('(../group/', page.read_text())
        self.assertEqual(json.loads((self.state / 'status.json').read_text())['mode'], 'failed')

    def test_concurrent_edit_is_not_overwritten(self):
        page = self.page('whatsapp/brain/weekly/2026-10-24.md', WEEKLY + '[daily](../group/2026-10-23.md)')
        def upload(stage):
            self.upload(stage)
            page.write_text('new concurrent draft')
        self.publish(upload)
        self.assertEqual(page.read_text(), 'new concurrent draft')

    def test_missing_or_non_digest_target_is_not_guessed(self):
        self.page('whatsapp/group/2026-10-23.md', DAILY.replace('type: topic', 'type: coverage-status'))
        self.page('whatsapp/brain/weekly/2026-10-24.md', WEEKLY + '[daily](../group/2026-10-23.md)')
        with self.assertRaisesRegex(ValueError, 'no last-good'):
            self.publish()
        self.assertEqual(self.uploads, [])

    def test_corrupt_cache_fails_closed(self):
        self.publish()
        (self.state / 'last-good.zip').write_bytes(b'corrupt')
        self.page('whatsapp/brain/overview.md', 'bad')
        with self.assertRaises(Exception):
            self.publish()
        self.assertEqual(len(self.uploads), 1)

    def test_symlink_escape_is_rejected(self):
        outside = self.root.parent / 'outside.md'
        outside.write_text(META)
        (self.root / 'whatsapp/brain/escape.md').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.publish()

    def test_empty_wiki_is_rejected(self):
        import shutil
        shutil.rmtree(self.root)
        self.root.mkdir()
        with self.assertRaisesRegex(ValueError, 'No knowledge pages'):
            self.publish()


if __name__ == '__main__':
    unittest.main()
