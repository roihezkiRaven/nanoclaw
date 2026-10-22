import { beforeEach, expect, it, vi } from 'vitest';
import type { DeliveryGuardSpec, GuardedDeliveryHandler } from '../../delivery-guard.js';
import { runGuarded } from '../../delivery-guard.js';
import type { Session } from '../../types.js';

const capture = vi.hoisted(() => ({
  actions: new Map<string, { handler: GuardedDeliveryHandler; spec: DeliveryGuardSpec }>(),
  folder: 'personal-assistant',
  approve: vi.fn(),
  notify: vi.fn(),
}));
vi.mock('../../delivery.js', () => ({
  registerDeliveryAction: (name: string, handler: GuardedDeliveryHandler, spec: DeliveryGuardSpec) =>
    capture.actions.set(name, { handler, spec }),
  reenterGuardedDeliveryAction: vi.fn(),
}));
vi.mock('../../db/agent-groups.js', () => ({ getAgentGroup: async () => ({ folder: capture.folder }) }));
vi.mock('../approvals/index.js', () => ({
  notifyAgent: capture.notify,
  requestApproval: capture.approve,
  registerApprovalHandler: vi.fn(),
}));
vi.mock('../../log.js', () => ({ log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));
import './index.js';
const session = { id: 'test', agent_group_id: 'pa' } as Session;
const payload = { action: 'assistant_mail_send', to: 'owner@example.com', subject: 'Trial', text: 'Exact message.' };
beforeEach(() => {
  capture.folder = 'personal-assistant';
  capture.approve.mockClear();
  capture.notify.mockClear();
});

it('holds outgoing mail without executing its credentialed handler', async () => {
  const entry = capture.actions.get('assistant_mail_send')!;
  const send = vi.fn();
  await runGuarded('assistant_mail_send', entry.spec, send, payload, session, null);
  expect(send).not.toHaveBeenCalled();
  expect(capture.approve).toHaveBeenCalledOnce();
  const card = capture.approve.mock.calls[0][0];
  expect(card.payload).toMatchObject(payload);
  expect(card.question).toContain(payload.text);
});

it('rejects other groups before reading or sending mail', async () => {
  capture.folder = 'whatsapp-brain';
  const entry = capture.actions.get('assistant_mail_read')!;
  const read = vi.fn();
  await runGuarded('assistant_mail_read', entry.spec, read, { action: 'assistant_mail_read' }, session, null);
  expect(read).not.toHaveBeenCalled();
  expect(capture.notify).toHaveBeenCalledWith(session, expect.stringContaining('only to the personal assistant'));
});
