import fs from 'node:fs/promises';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const mock = vi.hoisted(() => ({ folder: 'personal-assistant', query: vi.fn() }));
vi.mock('../../config.js', () => ({
  DATA_DIR: '/tmp/pa-diagnostics-test/data',
  GROUPS_DIR: '/tmp/pa-diagnostics-test/groups',
  INSTALL_SLUG: 'test',
}));
vi.mock('../../db/agent-groups.js', () => ({ getAgentGroup: async () => ({ folder: mock.folder }) }));
vi.mock('../../db/connection.js', () => ({ getDb: () => ({ all: mock.query }) }));
vi.mock('node:child_process', () => ({
  execFile: (...args: any[]) => {
    args.at(-1)(null, { stdout: 'active\n', stderr: '' });
  },
}));
import { diagnosticJson } from './diagnostics.js';
import { lookup } from '../registry.js';

beforeEach(async () => {
  mock.folder = 'personal-assistant';
  mock.query.mockReset();
  mock.query.mockResolvedValue([
    {
      approval_id: 'mine',
      status: 'pending',
      action: 'cli_command',
      created_at: '2026-10-18T12:00:00Z',
      platform_message_id: null,
      payload: JSON.stringify({ secret: 'must-not-leak', delivery: { status: 'failed' } }),
    },
  ]);
  await fs.mkdir('/tmp/pa-diagnostics-test/groups/personal-assistant/work', { recursive: true });
  await fs.writeFile(
    '/tmp/pa-diagnostics-test/groups/personal-assistant/work/state.json',
    JSON.stringify({
      records: {
        done: { id: 'done', status: 'done', verified_at: '2026-10-17T10:00:00Z', review_at: '2026-10-17T12:00:00Z' },
      },
    }),
  );
});
afterEach(() => fs.rm('/tmp/pa-diagnostics-test', { recursive: true, force: true }));

it('reports own approval failures and stale evidence without leaking approval payloads', async () => {
  const result = (await lookup('assistant-diagnostics')!.handler(
    {},
    { caller: 'agent', agentGroupId: 'g', sessionId: 's', messagingGroupId: 'dm' },
  )) as any;
  expect(result.approvals[0].delivery).toBe('failed');
  expect(JSON.stringify(result)).not.toContain('must-not-leak');
  expect(result.records[0]).toMatchObject({ status: 'done', overdue_review: true });
  expect(result.whatsapp).toMatchObject({ status: 'unavailable', complete_capture_verified: false });
  expect(mock.query.mock.calls[0].slice(1)).toEqual(['g', 'g']);
});

it('rejects other groups and preserves unavailable evidence as unknown', async () => {
  mock.folder = 'other';
  await expect(
    lookup('assistant-diagnostics')!.handler(
      {},
      { caller: 'agent', agentGroupId: 'foreign', sessionId: 's', messagingGroupId: 'dm' },
    ),
  ).rejects.toThrow('Personal Assistant');
  expect(mock.query).not.toHaveBeenCalled();
  expect(await diagnosticJson('/tmp/pa-diagnostics-test/missing')).toEqual({ status: 'unavailable' });
});
