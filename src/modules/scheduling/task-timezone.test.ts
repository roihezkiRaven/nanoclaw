import { afterEach, expect, it, vi } from 'vitest';
import { prepareScheduledTask } from './create.js';
import { taskTimezone, parseTaskContent } from './task-content.js';
import { handleRecurrence } from './recurrence.js';
vi.mock('../../container-config.js', () => ({ resolveGroupTimezone: vi.fn().mockResolvedValue('UTC') }));
vi.mock('./cancellation.js', () => ({ taskSessionCancelled: () => false }));
afterEach(() => vi.useRealTimers());

it.each([
  ['2026-03-26T14:00:00Z', '2026-03-26T18:00:00.000Z'],
  ['2026-03-27T14:00:00Z', '2026-03-27T17:00:00.000Z'],
  ['2026-10-24T15:00:00Z', '2026-10-24T17:00:00.000Z'],
  ['2026-10-25T15:00:00Z', '2026-10-25T18:00:00.000Z'],
])('keeps Jerusalem 20:00 across DST (%s)', async (now, expected) => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(now));
  const task = prepareScheduledTask({
    prompt: 'x',
    recurrence: '0 20 * * *',
    timezone: 'Asia/Jerusalem',
    taskTimezone: 'Asia/Jerusalem',
  });
  expect(task.processAfter).toBe(expected);
  const content = JSON.stringify({ prompt: 'x', timezone: task.timezone });
  const db = {
    getCompletedRecurring: () => [{ id: 'old', seriesId: 'series', recurrence: '0 20 * * *', content }],
    trailingFailedRuns: () => 0,
    armNextTask: vi.fn(),
  };
  await handleRecurrence(db as any, { id: 's', agent_group_id: 'g' } as any);
  expect(db.armNextTask).toHaveBeenCalledWith('old', expect.objectContaining({ processAfter: expected, content }));
});

it('rejects invalid zones, supports explicit default restoration and legacy content', () => {
  expect(() => taskTimezone('Mars/Unknown')).toThrow();
  expect(taskTimezone('none')).toBeNull();
  expect(taskTimezone('Asia/Jerusalem')).toBe('Asia/Jerusalem');
  expect(parseTaskContent('legacy prompt').timezone).toBeUndefined();
});
