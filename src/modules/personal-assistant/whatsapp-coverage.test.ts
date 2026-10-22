import { expect, it } from 'vitest';
import {
  initialCoverage,
  connectionCoverage,
  capturedCoverage,
  uploadedCoverage,
  ingestionCoverage,
} from './whatsapp-coverage.js';

it('tracks each group independently, retaining unknown history and disconnect gaps', () => {
  const state = initialCoverage(
    [
      { jid: 'a', label: 'A' },
      { jid: 'b', label: 'B' },
    ],
    '2026-10-18T10:00:00Z',
  );
  connectionCoverage(state, true, '2026-10-18T10:01:00Z');
  const record = { groupJid: 'a', timestamp: '2026-10-18T10:02:00Z' };
  capturedCoverage(state, record);
  uploadedCoverage(state, [record], { id: 'archive', modifiedTime: 'v1' }, '2026-10-18T10:03:00Z');
  uploadedCoverage(state, [record], { id: 'archive', modifiedTime: 'v1' }, '2026-10-18T10:03:00Z');
  connectionCoverage(state, false, '2026-10-18T10:04:00Z');
  const restored = JSON.parse(JSON.stringify(state));
  connectionCoverage(restored, true, '2026-10-18T10:05:00Z');
  const lag = ingestionCoverage(
    restored,
    { updated: '2026-10-18T10:00:00Z', sources: {} },
    Date.parse('2026-10-18T10:06:00Z'),
  );
  expect(lag.complete_capture_verified).toBe(false);
  expect(lag.observed_unprocessed_archives).toBe(1);
  expect(lag.groups[0]).toMatchObject({ captured: 1, uploaded: 1 });
  expect(lag.groups[1]).toMatchObject({ captured: 0, first: null, coverage: 'unverified' });
  expect(lag.possible_capture_gaps).toContainEqual({ from: '2026-10-18T10:04:00Z', until: '2026-10-18T10:05:00Z' });
  expect(ingestionCoverage(restored, { sources: { archive: { modified: 'v1' } } }).observed_unprocessed_archives).toBe(
    0,
  );
  expect(
    ingestionCoverage(restored, { sources: { archive: { modified: 'stale' } } }).observed_unprocessed_archives,
  ).toBe(1);
});

it('recognizes canonical Drive ingestion checkpoints', () => {
  const state = initialCoverage([], '2026-10-22T10:00:00Z');
  state.archives = [{ id: 'archive', modified: 'v1', at: '2026-10-22T10:00:00Z', groups: [] }];
  const checkpoint = { updated: '2026-10-22T10:00:00Z', files: { archive: { modifiedTime: 'v1' } } };
  const result = ingestionCoverage(state, checkpoint, Date.parse('2026-10-22T11:00:00Z'));
  expect(result.observed_unprocessed_archives).toBe(0);
  expect(result.ingestion_status).toBe('caught_up_for_retained_ledger');
  expect(ingestionCoverage(state, checkpoint, Date.parse('2026-10-24T11:00:00Z')).ingestion_status).toBe('stale');
});
