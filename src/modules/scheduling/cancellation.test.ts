import fs from 'node:fs';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('../../config.js', () => ({ DATA_DIR: '/tmp/pa-cancellation-fixture', TIMEZONE: 'UTC' }));
vi.mock('../../container-config.js', () => ({ resolveGroupTimezone: async () => 'UTC' }));
vi.mock('./run-log.js', () => ({ appendRunLog: vi.fn() }));
import { cancelTaskSession, taskSessionCancelled } from './cancellation.js';
import { handleRecurrence } from './recurrence.js';

afterEach(() => fs.rmSync('/tmp/pa-cancellation-fixture', { recursive: true, force: true }));
it('a durable marker prevents rearming a completed task after cancellation', async () => {
  cancelTaskSession('fixture');
  expect(taskSessionCancelled('fixture')).toBe(true);
  const mailbox = {
    getCompletedRecurring: () => [{ id: 'completed', recurrence: '0 20 * * *', seriesId: 'series', content: '{}' }],
    clearRecurrence: vi.fn(),
    armNextTask: vi.fn(),
  };
  await handleRecurrence(mailbox as any, { id: 'fixture', agent_group_id: 'g' } as any);
  expect(mailbox.clearRecurrence).toHaveBeenCalledWith('completed');
  expect(mailbox.armNextTask).not.toHaveBeenCalled();
});
