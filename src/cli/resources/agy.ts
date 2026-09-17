/** Bounded host-side bridge for the authenticated Antigravity CLI. */
import { execFile } from 'node:child_process';
import { copyFile, lstat, mkdtemp, open, realpath, rm, stat } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { promisify } from 'node:util';

import type { CallerContext } from '../frame.js';
import { register } from '../registry.js';
import { getAgentGroup } from '../../db/agent-groups.js';
import { AGY_MODELS } from '../../model-catalog.js';
import { sessionDir } from '../../session-manager.js';

const execFileAsync = promisify(execFile);
const MAX_PROMPT_BYTES = 32 * 1024;
const MAX_OUTPUT_BYTES = 256 * 1024;
const AGY_TIMEOUT_MS = 5 * 60 * 1000;
const MODEL_RE = /^(?:gemini|claude|gpt-oss)-[a-z0-9][a-z0-9._-]{0,79}$/i;
const EFFORTS = new Set(['low', 'medium', 'high']);
const MAX_MEDIA_BYTES = 256 * 1024 * 1024;
const MEDIA_PREFIX = '/workspace/inbox/';
const MEDIA_EXTENSIONS = new Set(['.mp4', '.mov', '.webm', '.avi']);

async function hasVideoSignature(filePath: string, extension: string): Promise<boolean> {
  const handle = await open(filePath, 'r');
  try {
    const header = Buffer.alloc(12);
    const { bytesRead } = await handle.read(header, 0, header.length, 0);
    if (bytesRead < 12) return false;
    if (extension === '.webm') return header.subarray(0, 4).equals(Buffer.from([0x1a, 0x45, 0xdf, 0xa3]));
    if (extension === '.avi')
      return header.subarray(0, 4).toString() === 'RIFF' && header.subarray(8, 12).toString() === 'AVI ';
    return header.subarray(4, 8).toString() === 'ftyp';
  } finally {
    await handle.close();
  }
}

function stringArg(args: Record<string, unknown>, name: string): string | undefined {
  const value = args[name];
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function parseAgyArgs(raw: Record<string, unknown>) {
  const prompt = stringArg(raw, 'prompt');
  if (!prompt) throw new Error('--prompt is required');
  if (Buffer.byteLength(prompt, 'utf8') > MAX_PROMPT_BYTES) {
    throw new Error(`--prompt exceeds ${MAX_PROMPT_BYTES} bytes`);
  }
  const model = stringArg(raw, 'model');
  if (model && (!MODEL_RE.test(model) || !AGY_MODELS.includes(model as (typeof AGY_MODELS)[number]))) {
    throw new Error('model is not in the approved Gemini Antigravity catalog');
  }
  const effort = stringArg(raw, 'effort')?.toLowerCase();
  if (effort && !EFFORTS.has(effort)) throw new Error('--effort must be low, medium, or high');
  return { prompt, model, effort };
}

function parseAgyMediaArgs(raw: Record<string, unknown>) {
  const parsed = parseAgyArgs(raw);
  const mediaPath = stringArg(raw, 'path');
  if (!mediaPath) throw new Error('--path is required');
  if (!mediaPath.startsWith(MEDIA_PREFIX) || mediaPath.includes('..')) {
    throw new Error('--path must be one explicitly selected video under /workspace/inbox/');
  }
  const extension = path.extname(mediaPath).toLowerCase();
  if (!MEDIA_EXTENSIONS.has(extension)) {
    throw new Error('video must be .mp4, .mov, .webm, or .avi');
  }
  return { ...parsed, mediaPath };
}

type AgyResponse = {
  status?: string;
  response?: string;
  duration_seconds?: number;
  usage?: Record<string, unknown>;
};

async function runAgy(args: ReturnType<typeof parseAgyArgs>, ctx: CallerContext) {
  if (ctx.caller !== 'agent') throw new Error('agy-run is only available from an agent session');
  const group = await getAgentGroup(ctx.agentGroupId);
  if (group?.folder !== 'personal-assistant') {
    throw new Error('agy-run is only available to the Personal Assistant master group');
  }
  if (!ctx.sessionId) throw new Error('agy-run requires a session context');
  const workspace = sessionDir(ctx.agentGroupId, ctx.sessionId);
  const cliArgs = ['-p', args.prompt, '--output-format', 'json', '--sandbox', '--add-dir', workspace];
  if (args.model) cliArgs.push('--model', args.model);
  if (args.effort) cliArgs.push('--effort', args.effort);
  const { stdout } = await execFileAsync(process.env.AGY_BIN || '/home/assistant/.local/bin/agy', cliArgs, {
    cwd: workspace,
    env: {
      PATH: '/home/assistant/.local/bin:/usr/local/bin:/usr/bin:/bin',
      HOME: process.env.HOME || '/home/assistant',
    },
    timeout: AGY_TIMEOUT_MS,
    maxBuffer: MAX_OUTPUT_BYTES,
    windowsHide: true,
  });
  let parsed: AgyResponse;
  try {
    parsed = JSON.parse(stdout) as AgyResponse;
  } catch (error) {
    throw new Error('Antigravity returned invalid JSON', { cause: error });
  }
  if (parsed.status !== 'SUCCESS' || typeof parsed.response !== 'string') {
    throw new Error(`Antigravity failed (${parsed.status ?? 'unknown status'})`);
  }
  return {
    response: parsed.response,
    duration_seconds: parsed.duration_seconds ?? null,
    usage: parsed.usage ?? null,
    model: args.model ?? 'subscription default',
    note: 'Executed in the current session workspace. AGY may inspect and edit files there, but host credentials, Drive mounts, databases, and other sessions are not exposed.',
  };
}

async function runAgyMedia(args: ReturnType<typeof parseAgyMediaArgs>, ctx: CallerContext) {
  if (ctx.caller !== 'agent') throw new Error('agy-media-run is only available from an agent session');
  const group = await getAgentGroup(ctx.agentGroupId);
  if (group?.folder !== 'personal-assistant') {
    throw new Error('agy-media-run is only available to the Personal Assistant master group');
  }
  if (!ctx.sessionId) throw new Error('agy-media-run requires a session context');

  const inboxRoot = path.join(sessionDir(ctx.agentGroupId, ctx.sessionId), 'inbox');
  const requested = path.resolve('/', args.mediaPath.slice('/'.length));
  const source = path.resolve(sessionDir(ctx.agentGroupId, ctx.sessionId), requested.slice('/workspace/'.length));
  const resolvedInbox = path.resolve(inboxRoot);
  if (source !== resolvedInbox && !source.startsWith(`${resolvedInbox}${path.sep}`)) {
    throw new Error('selected video is outside the session inbox');
  }
  const sourceInfo = await lstat(source);
  if (!sourceInfo.isFile() || sourceInfo.isSymbolicLink()) throw new Error('selected video is not a regular file');
  const realSource = await realpath(source);
  if (realSource !== source) throw new Error('selected video may not be a symlink');
  const sourceStat = await stat(source);
  if (sourceStat.size > MAX_MEDIA_BYTES) throw new Error(`video exceeds ${MAX_MEDIA_BYTES} bytes`);
  if (!(await hasVideoSignature(source, path.extname(source).toLowerCase()))) {
    throw new Error('selected file does not have a valid video container signature');
  }

  const cwd = await mkdtemp(`${tmpdir()}/nanoclaw-agy-media-`);
  const stagedPath = path.join(cwd, path.basename(source));
  try {
    await copyFile(source, stagedPath);
    const mediaPrompt = `${args.prompt}\n\nAnalyze the explicitly selected video at ${stagedPath}. Do not modify files. If it cannot be inspected, say so clearly.`;
    const cliArgs = ['-p', mediaPrompt, '--output-format', 'json', '--sandbox', '--add-dir', cwd];
    if (args.model) cliArgs.push('--model', args.model);
    if (args.effort) cliArgs.push('--effort', args.effort);
    const { stdout } = await execFileAsync(process.env.AGY_BIN || '/home/assistant/.local/bin/agy', cliArgs, {
      cwd,
      env: {
        PATH: '/home/assistant/.local/bin:/usr/local/bin:/usr/bin:/bin',
        HOME: process.env.HOME || '/home/assistant',
      },
      timeout: AGY_TIMEOUT_MS,
      maxBuffer: MAX_OUTPUT_BYTES,
      windowsHide: true,
    });
    let parsed: AgyResponse;
    try {
      parsed = JSON.parse(stdout) as AgyResponse;
    } catch (error) {
      throw new Error('Antigravity returned invalid JSON', { cause: error });
    }
    if (parsed.status !== 'SUCCESS' || typeof parsed.response !== 'string') {
      throw new Error(`Antigravity failed (${parsed.status ?? 'unknown status'})`);
    }
    return {
      response: parsed.response,
      duration_seconds: parsed.duration_seconds ?? null,
      usage: parsed.usage ?? null,
      model: args.model ?? 'subscription default',
      media: {
        filename: path.basename(source),
        bytes: sourceStat.size,
        type: path.extname(source).slice(1).toLowerCase(),
      },
      note: 'Only the explicitly selected session attachment was copied into a temporary AGY workspace; Drive, NanoClaw, and credentials were not mounted.',
    };
  } finally {
    await rm(cwd, { recursive: true, force: true });
  }
}

register({
  name: 'agy-run',
  description: 'Run one bounded Antigravity CLI request using the owner-authenticated subscription session.',
  access: 'open',
  action: 'agy.run',
  parseArgs: parseAgyArgs,
  handler: runAgy,
});

register({
  name: 'agy-media-run',
  description: 'Analyze one explicitly selected video attachment with the owner-authenticated Antigravity CLI.',
  access: 'open',
  action: 'agy.media.run',
  parseArgs: parseAgyMediaArgs,
  handler: runAgyMedia,
});
