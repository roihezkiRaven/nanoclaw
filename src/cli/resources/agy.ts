/** Bounded host-side bridge for the authenticated Antigravity CLI. */
import { execFile } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { promisify } from 'node:util';

import type { CallerContext } from '../frame.js';
import { register } from '../registry.js';
import { getAgentGroup } from '../../db/agent-groups.js';

const execFileAsync = promisify(execFile);
const MAX_PROMPT_BYTES = 32 * 1024;
const MAX_OUTPUT_BYTES = 256 * 1024;
const AGY_TIMEOUT_MS = 5 * 60 * 1000;
const MODEL_RE = /^(?:gemini|claude|gpt-oss)-[a-z0-9][a-z0-9._-]{0,79}$/i;
const EFFORTS = new Set(['low', 'medium', 'high']);

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
  if (model && !MODEL_RE.test(model)) throw new Error('invalid Antigravity model name');
  const effort = stringArg(raw, 'effort')?.toLowerCase();
  if (effort && !EFFORTS.has(effort)) throw new Error('--effort must be low, medium, or high');
  return { prompt, model, effort };
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
  const cwd = await mkdtemp(`${tmpdir()}/nanoclaw-agy-`);
  try {
    const cliArgs = ['-p', args.prompt, '--output-format', 'json', '--sandbox'];
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
      note: 'Executed in a temporary sandbox directory; no NanoClaw files were mounted.',
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
