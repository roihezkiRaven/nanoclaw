import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
vi.mock('../../container-restart.js', () => ({ restartAgentGroupContainers: vi.fn() }));
vi.mock('../../db/agent-groups.js', () => ({ getAgentGroup: vi.fn() }));
vi.mock('node:fs/promises', () => ({
  default: { readFile: vi.fn(), realpath: vi.fn(), lstat: vi.fn(), writeFile: vi.fn() },
}));
import { getAgentGroup } from '../../db/agent-groups.js';
import { lookup } from '../registry.js';
import { parsePatch, sourcePath } from './host-changes.js';

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getAgentGroup).mockResolvedValue({ folder: 'personal-assistant' } as Awaited<
    ReturnType<typeof getAgentGroup>
  >);
});
afterEach(() => vi.unstubAllEnvs());

it('permits capability source but rejects paths to host identity, policy and secrets', () => {
  expect(sourcePath('src/cli/resources/video.ts')).toBe('src/cli/resources/video.ts');
  for (const file of [
    '.env',
    'src/config.ts',
    'src/guard/index.ts',
    '/src/cli/resources/video.ts',
    'src/cli/resources/../config.ts',
    'src/cli/resources/video.ts/extra',
    'src/cli/resources/a\\b.ts',
  ])
    expect(() => sourcePath(file)).toThrow();
});
it('requires bounded text and relevant host tests before preparing a patch', () => {
  const input = {
    files: { 'src/cli/resources/video.ts': 'export const video = true;' },
    tests: ['src/cli/resources/video.test.ts'],
    summary: 'Support selected videos',
  };
  expect(parsePatch(input)).toEqual(input);
  for (const bad of [
    { ...input, tests: [] },
    { ...input, tests: ['src/cli/resources/video.ts'] },
    { ...input, files: { '.env': 'secret' } },
    { ...input, files: { 'src/cli/resources/host-changes.ts': 'replace approval controller' } },
    { ...input, files: {} },
    { ...input, files: { 'src/cli/resources/video.ts': 'x'.repeat(512 * 1024 + 1) } },
  ])
    expect(() => parsePatch(bad)).toThrow();
});

it('keeps activation behind native approval and rejects a substituted diff before writing', async () => {
  const command = lookup('host-change-apply')!;
  expect(command.access).toBe('approval');
  vi.stubEnv('INVOCATION_ID', 'supervised-test');
  vi.mocked(getAgentGroup).mockResolvedValue({ folder: 'personal-assistant' } as Awaited<
    ReturnType<typeof getAgentGroup>
  >);
  const files = { 'src/cli/resources/video.ts': 'export const video = true;' };
  const baseline = { 'src/cli/resources/video.ts': null };
  const digest = createHash('sha256').update(JSON.stringify({ files, baseline })).digest('hex');
  vi.mocked(fs.readFile).mockResolvedValue(
    JSON.stringify({ group: 'group', files, baseline, digest, diff: 'exact tested diff' }),
  );
  const args = command.parseArgs({ id: '12345678-1234-1234-1234-123456789abc', digest, diff: 'substituted diff' });
  await expect(
    command.handler(args, { caller: 'agent', agentGroupId: 'group', sessionId: 'session', messagingGroupId: 'dm' }),
  ).rejects.toThrow('Approval does not match');
  expect(fs.writeFile).not.toHaveBeenCalled();
  vi.unstubAllEnvs();
});

it('rejects source drift after testing instead of overwriting a concurrent edit', async () => {
  const command = lookup('host-change-apply')!;
  vi.stubEnv('INVOCATION_ID', 'supervised-test');
  const files = { 'src/cli/resources/video.ts': 'export const video = true;' };
  const baseline = { 'src/cli/resources/video.ts': 'original' };
  const digest = createHash('sha256').update(JSON.stringify({ files, baseline })).digest('hex');
  const draft = {
    group: 'group',
    files,
    baseline,
    digest,
    diff: 'exact tested diff',
    tests: ['src/cli/resources/video.test.ts'],
    summary: 'Selected video capability',
  };
  vi.mocked(fs.readFile).mockImplementation(async (file) =>
    String(file).endsWith('draft.json')
      ? JSON.stringify(draft)
      : String(file).endsWith('activation.json')
        ? Promise.reject(Object.assign(new Error('missing'), { code: 'ENOENT' }))
        : 'concurrent edit',
  );
  vi.mocked(fs.realpath).mockImplementation(async (file) => String(file));
  vi.mocked(fs.lstat).mockResolvedValue({ isSymbolicLink: () => false } as Awaited<ReturnType<typeof fs.lstat>>);
  const args = command.parseArgs({ id: '12345678-1234-1234-1234-123456789abc', digest, diff: draft.diff });
  await expect(
    command.handler(args, { caller: 'agent', agentGroupId: 'group', sessionId: 'session', messagingGroupId: 'dm' }),
  ).rejects.toThrow('Host source changed');
  expect(fs.writeFile).not.toHaveBeenCalled();
  vi.unstubAllEnvs();
});

it('allows integration repairs and larger immutable review while keeping controllers protected', () => {
  for (const file of [
    'tools/gdrive_broker.py',
    'tools/gdrive_broker_test.py',
    'tools/whatsapp_collector.ts',
    'src/modules/scheduling/recurrence.ts',
  ])
    expect(sourcePath(file)).toBe(file);
  expect(
    parsePatch({
      files: { 'tools/gdrive_broker.py': '# '.repeat(40000) },
      tests: ['tools/gdrive_broker_test.py'],
      summary: 'Pagination',
    }).tests,
  ).toEqual(['tools/gdrive_broker_test.py']);
  for (const file of [
    'tools/maintenance_supervisor.py',
    'src/modules/approvals/primitive.ts',
    'src/guard/index.ts',
    'config/google/reader-token.json',
  ])
    expect(() => sourcePath(file)).toThrow();
  const command = lookup('host-change-apply')!;
  expect(
    command.parseArgs({
      id: '12345678-1234-1234-1234-123456789abc',
      digest: 'a'.repeat(64),
      diff_sha256: 'b'.repeat(64),
      summary: 'Pagination',
      paths: ['tools/gdrive_broker.py'],
    }),
  ).toMatchObject({ diff_sha256: 'b'.repeat(64) });
});
