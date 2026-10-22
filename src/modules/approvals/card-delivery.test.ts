import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ rows: new Map<string, any>(), adapter: undefined as any }));
vi.mock('../../db/sessions.js', () => ({
  createPendingApproval: async (row: any) => {
    mocks.rows.set(row.approval_id, { status: 'pending', ...row });
    return true;
  },
  getPendingApproval: async (id: string) => mocks.rows.get(id),
  getSession: vi.fn(),
}));
vi.mock('../../db/connection.js', () => ({
  getDb: () => ({
    run: async (_sql: string, payload: string, message: string, id: string) => {
      Object.assign(mocks.rows.get(id), { payload, platform_message_id: message });
      return { changes: 1 };
    },
  }),
}));
vi.mock('../../db/messaging-groups.js', () => ({ getMessagingGroup: vi.fn() }));
vi.mock('../permissions/user-dm.js', () => ({
  ensureUserDm: async () => ({ channel_type: 'telegram', platform_id: 'dm' }),
}));
vi.mock('../../delivery.js', () => ({ getDeliveryAdapter: () => mocks.adapter }));
vi.mock('../../request-wake.js', () => ({ requestWake: vi.fn() }));
vi.mock('../../session-manager.js', () => ({ writeSessionMessage: vi.fn() }));
import { requestApproval, retryApprovalDelivery } from './primitive.js';

beforeEach(() => {
  mocks.rows.clear();
  mocks.adapter = undefined;
});
const request = () =>
  requestApproval({
    session: { id: 's', agent_group_id: 'g', messaging_group_id: null } as any,
    agentName: 'PA',
    action: 'cli_command',
    payload: { frame: { command: 'host-change-apply' } },
    title: 'Approve patch',
    question: 'Exact digest',
    approverUserId: 'telegram:owner',
  });

it('retains unavailable delivery as explicit evidence instead of claiming a sent card', async () => {
  const result = await request();
  expect(result.delivery).toBe('unavailable');
  expect(JSON.parse(mocks.rows.get(result.approval_id!).payload).delivery.status).toBe('unavailable');
});

it('retries failed cards with the same decision ID, saves receipt and avoids repeat sends', async () => {
  const deliver = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValue('telegram-message-1');
  mocks.adapter = { deliver };
  const result = await request();
  expect(result.delivery).toBe('failed');
  expect(await retryApprovalDelivery(result.approval_id!)).toBe('delivered');
  expect(await retryApprovalDelivery(result.approval_id!)).toBe('delivered');
  expect(deliver).toHaveBeenCalledTimes(2);
  expect(mocks.rows.get(result.approval_id!).platform_message_id).toBe('telegram-message-1');
  expect(mocks.rows.get(result.approval_id!).status).toBe('pending');
  expect(JSON.parse(deliver.mock.calls[0][4]).questionId).toBe(JSON.parse(deliver.mock.calls[1][4]).questionId);
});

it('an adapter acknowledgment without a receipt is unverified, not delivered', async () => {
  mocks.adapter = { deliver: vi.fn().mockResolvedValue(undefined) };
  expect((await request()).delivery).toBe('unverified');
});
