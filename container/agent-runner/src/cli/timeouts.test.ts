import { expect, test } from 'bun:test';
import { commandTimeoutMs } from './timeouts.js';

test('workers can finish while ordinary CLI requests keep the short timeout', () => {
  expect(commandTimeoutMs('agy-media-run')).toBe(1080000);
  expect(commandTimeoutMs('agy-run')).toBe(360000);
  expect(commandTimeoutMs('host-change-stage')).toBe(300000);
  expect(commandTimeoutMs('host-change-apply')).toBe(300000);
  expect(commandTimeoutMs('groups-get')).toBe(30000);
});
