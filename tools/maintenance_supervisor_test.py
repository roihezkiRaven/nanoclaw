import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import maintenance_supervisor as m


class SupervisorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'data/.host-change-drafts/123'
        self.directory.mkdir(parents=True)
        (self.directory.parent / '.activation-lock').mkdir()
        (self.root / 'src').mkdir()
        (self.root / 'src/example.ts').write_text('candidate')
        self.plan = {'state': 'built', 'unit': 'nanoclaw-v2-test.service', 'group': 'g', 'old_pid': 1,
                     'baseline': {'src/example.ts': 'previous'}, 'candidate': {'src/example.ts': 'candidate'}}
        (self.directory / 'activation.json').write_text(json.dumps(self.plan))

    def state(self):
        return json.loads((self.directory / 'activation.json').read_text())['state']

    def test_only_marks_applied_after_restart_health(self):
        with patch.object(m, 'run') as run, patch.object(m, 'wait_healthy') as health, patch.object(m.time, 'sleep'):
            self.assertFalse((self.directory / 'applied.json').exists())
            m.supervise(self.root, '123')
            health.assert_called_once()
            self.assertTrue((self.directory / 'applied.json').exists())
            self.assertEqual(self.state(), 'healthy')

    def test_failed_health_restores_previous_source_and_checks_recovery(self):
        with patch.object(m, 'run') as run, patch.object(m, 'wait_healthy', side_effect=[RuntimeError('bad health'), None]) as health, patch.object(m.time, 'sleep'):
            m.supervise(self.root, '123')
            self.assertEqual(health.call_count, 2)
            self.assertEqual((self.root / 'src/example.ts').read_text(), 'previous')
            self.assertEqual(self.state(), 'rolled_back')
            self.assertFalse((self.directory / 'applied.json').exists())
            self.assertTrue(any('node_modules/typescript/bin/tsc' in call.args[1] for call in run.call_args_list))

    def test_failed_recovery_is_failed_not_success(self):
        with patch.object(m, 'run'), patch.object(m, 'wait_healthy', side_effect=RuntimeError()), patch.object(m.time, 'sleep'):
            m.supervise(self.root, '123')
            self.assertEqual(self.state(), 'failed')

    def test_source_drift_never_overwrites_external_edits(self):
        (self.root / 'src/example.ts').write_text('external')
        with patch.object(m, 'run') as run:
            m.supervise(self.root, '123')
            run.assert_not_called()
        self.assertEqual((self.root / 'src/example.ts').read_text(), 'external')
        self.assertEqual(self.state(), 'conflict')

    def test_stable_health_requires_new_pid_and_real_cli_success(self):
        with patch.object(m, 'run', side_effect=[MagicMock(), MagicMock(stdout='1'), MagicMock(stdout='{"ok":true}')]):
            with self.assertRaises(RuntimeError): m.healthy(self.root, self.plan)


if __name__ == '__main__':
    unittest.main()
