"""Exercise actual broker handlers and the shared Drive destination boundary."""
import unittest
from unittest.mock import MagicMock, patch

import gdrive_broker as broker

ROOT = 'approved_root_123'
CHILD = 'child_folder_123'
NESTED = 'nested_folder_123'
OUTSIDE = 'outside_folder_123'
FOLDER = 'application/vnd.google-apps.folder'


class DrivePlacementTest(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            ROOT: {'mimeType': FOLDER, 'parents': ['outside_parent_123'], 'trashed': False},
            CHILD: {'mimeType': FOLDER, 'parents': [ROOT], 'trashed': False},
            NESTED: {'mimeType': FOLDER, 'parents': [CHILD], 'trashed': False},
            OUTSIDE: {'mimeType': FOLDER, 'parents': [], 'trashed': False},
        }
        self.api = MagicMock()
        self.api.files().get.side_effect = self.get_file
        self.api.files().create.side_effect = self.create_file
        self.patches = [patch.object(broker.drive, 'env_value', return_value=ROOT),
                        patch.object(broker.drive, 'service', return_value=self.api)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.handler = object.__new__(broker.Handler)

    def test_list_and_search_continue_beyond_fifty_files(self):
        for action, args in [('list', {'folder_id': CHILD}), ('search', {'query': 'report'})]:
            self.api.files().list.side_effect = lambda **kw: MagicMock(execute=lambda: (
                {'files': [{'id': str(i)} for i in range(50)], 'nextPageToken': 'second'}
                if not kw.get('pageToken') else {'files': [{'id': str(i)} for i in range(50, 61)]}))
            first = self.handler.process({'action': action, 'limit': 50, **args})
            self.assertFalse(first['complete'])
            second = self.handler.process({'action': action, 'page_token': first['next_page_token'], **args})
            self.assertTrue(second['complete'])
            self.assertEqual(len(first['files'] + second['files']), 61)

    def test_read_discloses_truncation_and_continues_unicode_without_loss(self):
        text = 'א🙂a' * 300000
        self.api.files().get.side_effect = None
        self.api.files().get.return_value.execute.return_value = {'name': 'large.txt', 'mimeType': 'text/plain', 'version': '7'}
        self.api.files().get_media.return_value.execute.return_value = text.encode()
        combined = ''; offset = 0
        while True:
            result = self.handler.process({'action': 'read', 'file_id': 'large', 'offset': offset, **({'version': '7'} if offset else {})})
            self.assertLessEqual(result['returned_bytes'], broker.MAX_BYTES)
            combined += result['text']
            if result['complete']: break
            self.assertTrue(result['truncated'])
            offset = result['next_offset']
        self.assertEqual(combined, text)
        with self.assertRaises(ValueError):
            self.handler.process({'action': 'read', 'file_id': 'large', 'offset': 2, 'version': 'changed'})
        with self.assertRaises(ValueError):
            self.handler.process({'action': 'read', 'file_id': 'large', 'offset': 2})

    def test_read_rejects_source_drift_during_download(self):
        self.api.files().get.side_effect = None
        self.api.files().get.return_value.execute.side_effect = [
            {'name': 'x', 'mimeType': 'text/plain', 'version': '1'},
            {'name': 'x', 'mimeType': 'text/plain', 'version': '2'},
        ]
        self.api.files().get_media.return_value.execute.return_value = b'changed'
        with self.assertRaisesRegex(ValueError, 'changed during read'):
            self.handler.process({'action': 'read', 'file_id': 'file'})

    def get_file(self, fileId, **kwargs):
        if fileId not in self.metadata:
            raise ValueError('file not found or inaccessible')
        return MagicMock(execute=lambda: self.metadata[fileId])

    def create_file(self, body, **kwargs):
        self.metadata['new_file_123'] = {**body, 'id': 'new_file_123', 'trashed': False}
        return MagicMock(execute=lambda: self.metadata['new_file_123'])

    def test_writes_keep_default_root_child_and_nested_destinations(self):
        for parent in [None, ROOT, CHILD, NESTED]:
            with self.subTest(parent=parent):
                result = self.handler.process({'action': 'write', 'name': 'test.txt', 'text': 'content', 'parent_id': parent})
                self.assertEqual(result['file']['parents'], [ROOT if parent is None else parent])
                self.assertEqual(self.api.files().create.call_args.kwargs['body']['parents'], result['file']['parents'])

    def test_mkdir_keeps_nested_parent_and_returns_readback_metadata(self):
        result = self.handler.process({'action': 'mkdir', 'name': 'test folder', 'parent_id': CHILD})
        self.assertEqual(result['folder']['parents'], [CHILD])
        self.assertEqual(self.api.files().get.call_args.kwargs['fileId'], 'new_file_123')

    def assert_destination_rejected(self, destination):
        self.api.files().create.reset_mock()
        with self.assertRaises((ValueError, RuntimeError)):
            self.handler.process({'action': 'write', 'name': 'test.txt', 'text': 'content', 'parent_id': destination})
        self.api.files().create.assert_not_called()

    def test_outside_missing_and_malformed_destinations_never_create(self):
        for parent in [OUTSIDE, 'missing_folder_123', '', 'bad/id', 0, False, [], {}]:
            with self.subTest(parent=parent):
                self.assert_destination_rejected(parent)

    def test_deleted_nonfolder_shortcut_and_cyclic_ancestry_never_create(self):
        for change in [
            {'trashed': True}, {'mimeType': 'text/plain'},
            {'mimeType': 'application/vnd.google-apps.shortcut'},
            {'parents': [CHILD]}, {'parents': [ROOT, OUTSIDE]},
        ]:
            with self.subTest(change=change):
                self.metadata[CHILD] = {'mimeType': FOLDER, 'parents': [ROOT], 'trashed': False, **change}
                self.assert_destination_rejected(CHILD)

    def test_invalid_or_deleted_root_and_deleted_ancestor_never_create(self):
        for target, change in [(ROOT, {'trashed': True}), (ROOT, {'mimeType': 'text/plain'}), (CHILD, {'trashed': True})]:
            with self.subTest(target=target, change=change):
                original = self.metadata[target]
                self.metadata[target] = {**original, **change}
                self.assert_destination_rejected(NESTED)
                self.metadata[target] = original

    def test_missing_root_configuration_fails_explicitly(self):
        with patch.object(broker.drive, 'env_value', return_value=''):
            self.assert_destination_rejected(None)

    def test_cli_and_broker_use_the_same_destination_validator(self):
        self.assertIs(broker.writer_parent, broker.drive.writer_parent)

    def test_validation_reads_with_reader_but_creation_and_readback_use_writer(self):
        reader, writer = MagicMock(), MagicMock()
        reader.files().get.side_effect = self.get_file
        writer.files().get.side_effect = self.get_file
        writer.files().create.side_effect = self.create_file
        with patch.object(broker.drive, 'service', side_effect=lambda mode, authorize: reader if mode == 'reader' else writer):
            result = self.handler.process({'action': 'write', 'name': 'test.txt', 'text': 'content', 'parent_id': CHILD})
        self.assertEqual(result['file']['parents'], [CHILD])
        reader.files().create.assert_not_called()
        writer.files().create.assert_called_once()
        self.assertEqual([c.kwargs['fileId'] for c in reader.files().get.call_args_list], [CHILD, ROOT])
        self.assertEqual(writer.files().get.call_args.kwargs['fileId'], 'new_file_123')

    def test_wrong_persisted_parent_is_not_reported_as_success(self):
        def misplaced(body, **kwargs):
            return self.create_file({**body, 'parents': [ROOT]})
        self.api.files().create.side_effect = misplaced
        with self.assertRaisesRegex(RuntimeError, 'new_file_123.*unexpected placement'):
            self.handler.process({'action': 'write', 'name': 'test.txt', 'text': 'content', 'parent_id': CHILD})

    def test_failed_readback_identifies_created_file_and_warns_against_retry(self):
        self.api.files().create.return_value.execute.return_value = {'id': 'unreadable_file_123'}
        self.api.files().create.side_effect = None
        with self.assertRaisesRegex(RuntimeError, 'unreadable_file_123.*inspect it before retrying'):
            self.handler.process({'action': 'write', 'name': 'test.txt', 'text': 'content', 'parent_id': CHILD})


if __name__ == '__main__':
    unittest.main()
