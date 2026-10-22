import { expect, it, vi } from 'vitest';

vi.mock('node:child_process', () => ({ execFile: vi.fn() }));
vi.mock('../../db/agent-groups.js', () => ({ getAgentGroup: vi.fn() }));
vi.mock('../../session-manager.js', () => ({ sessionDir: vi.fn() }));
import { parseAgyMediaArgs } from './agy.js';

it('accepts one Drive video ID or one inbox attachment and Argon models', () => {
  expect(
    parseAgyMediaArgs({ prompt: 'Analyze', file_id: 'selected_video_123', model: 'gemini-4-argon-high' }),
  ).toMatchObject({ fileId: 'selected_video_123', model: 'gemini-4-argon-high' });
  expect(parseAgyMediaArgs({ prompt: 'Analyze', path: '/workspace/inbox/message/video.mp4' })).toMatchObject({
    mediaPath: '/workspace/inbox/message/video.mp4',
  });
});

it('rejects ambiguous sources, unsafe paths, unsupported files, and unknown models', () => {
  for (const source of [
    {},
    { file_id: 'bad/id' },
    { file_id: 'selected_video_123', path: '/workspace/inbox/video.mp4' },
    { path: '/workspace/inbox/../video.mp4' },
    { path: '/etc/video.mp4' },
    { path: '/workspace/inbox/video.txt' },
    { file_id: 'selected_video_123', model: 'gemini-unknown' },
    { file_id: 'selected_video_123', start_seconds: -1 },
    { file_id: 'selected_video_123', duration_seconds: 0 },
    { file_id: 'selected_video_123', duration_seconds: '20' },
  ])
    expect(() => parseAgyMediaArgs({ prompt: 'Analyze', ...source })).toThrow();
});

it('stages only selected Drive media and cleans the private workspace on success and failure', async () => {
  const { execFile } = await import('node:child_process');
  const { getAgentGroup } = await import('../../db/agent-groups.js');
  const fs = await import('node:fs/promises');
  const { lookup } = await import('../registry.js');
  vi.mocked(getAgentGroup).mockResolvedValue({ folder: 'personal-assistant' } as Awaited<
    ReturnType<typeof getAgentGroup>
  >);
  let staging = '';
  let fail = false;
  vi.mocked(execFile).mockImplementation((...parameters: unknown[]) => {
    const [binary, rawArgs, rawOptions, rawCallback] = parameters;
    const args = rawArgs as string[];
    const options = rawOptions as { cwd?: string };
    const callback = rawCallback as (error: Error | null, result?: { stdout: string; stderr: string }) => void;
    void (async () => {
      let result;
      if (String(binary).endsWith('/python')) {
        staging = args[args.indexOf('--output-dir') + 1];
        const mediaPath = `${staging}/selected-video.mp4`;
        await fs.writeFile(mediaPath, '0000ftyp0000');
        result = { path: mediaPath, name: 'Selected recording.mp4', file_id: 'selected_video_123', version: '1' };
      } else if (String(binary).endsWith('ffprobe'))
        result = { format: { duration: '20' }, streams: [{ codec_type: 'video' }] };
      else {
        expect(args.filter((arg) => arg === '--add-dir')).toHaveLength(1);
        expect(options.cwd).toBe(staging);
        if (fail) return callback(new Error('worker timeout'));
        result = { status: 'SUCCESS', response: 'Actual video observations' };
      }
      callback(null, { stdout: JSON.stringify(result), stderr: '' });
    })().catch(callback);
    return {} as ReturnType<typeof execFile>;
  });
  const command = lookup('agy-media-run')!;
  const args = parseAgyMediaArgs({ prompt: 'Analyze', file_id: 'selected_video_123' });
  const ctx = { caller: 'agent' as const, sessionId: 'session', agentGroupId: 'group', messagingGroupId: 'dm' };
  expect(await command.handler(args, ctx)).toMatchObject({
    response: 'Actual video observations',
    media: { source: { file_id: 'selected_video_123' } },
  });
  await expect(fs.stat(staging)).rejects.toThrow();
  fail = true;
  await expect(command.handler(args, ctx)).rejects.toThrow('worker timeout');
  await expect(fs.stat(staging)).rejects.toThrow();
});
