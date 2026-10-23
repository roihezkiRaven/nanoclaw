import json
from pathlib import Path
import tempfile
import unittest
import maintenance_bootstrap as bootstrap


class BootstrapBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'; self.root.mkdir()
        self.release = Path(self.temp.name) / 'release'; self.release.mkdir()
        (self.root / 'src').mkdir(); (self.root / 'src/example.ts').write_bytes(b'before')
        payload = self.release / 'payload/src'; payload.mkdir(parents=True)
        (payload / 'example.ts').write_bytes(b'after')
        self.manifest = {'artifacts': {}, 'files': {'src/example.ts': {
            'baseline_sha256': bootstrap.digest(b'before'), 'sha256': bootstrap.digest(b'after')}}}
        self.save_manifest()

    def save_manifest(self):
        raw = json.dumps(self.manifest).encode()
        (self.release / 'manifest.json').write_bytes(raw)
        self.approved = bootstrap.digest(raw)

    def test_matching_preflight_never_changes_production(self):
        self.assertEqual(bootstrap.verify_release(self.release, self.root, self.approved), self.manifest)
        self.assertEqual((self.root / 'src/example.ts').read_bytes(), b'before')

    def test_rejects_unapproved_or_modified_candidates(self):
        with self.assertRaisesRegex(RuntimeError, 'approved digest'):
            bootstrap.verify_release(self.release, self.root, '0' * 64)
        (self.release / 'payload/src/example.ts').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'Candidate source drift'):
            bootstrap.verify_release(self.release, self.root, self.approved)

    def test_stops_on_production_drift_instead_of_rebasing_approval(self):
        (self.root / 'src/example.ts').write_bytes(b'newer owner edit')
        with self.assertRaisesRegex(RuntimeError, 'Production source drift'):
            bootstrap.verify_release(self.release, self.root, self.approved)
        self.assertEqual((self.root / 'src/example.ts').read_bytes(), b'newer owner edit')

    def test_rejects_credentials_and_symlink_destinations(self):
        self.manifest['files']['.env'] = self.manifest['files']['src/example.ts']
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, 'Forbidden bootstrap target'):
            bootstrap.verify_release(self.release, self.root, self.approved)
        del self.manifest['files']['.env']; self.save_manifest()
        (self.root / 'src/example.ts').unlink()
        (self.root / 'src/example.ts').symlink_to(self.release / 'payload/src/example.ts')
        with self.assertRaisesRegex(RuntimeError, 'Symlink target'):
            bootstrap.verify_release(self.release, self.root, self.approved)


if __name__ == '__main__':
    unittest.main()
