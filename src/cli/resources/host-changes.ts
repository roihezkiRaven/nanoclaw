/** Small capability patches: isolated checks, immutable draft, exact owner approval. */
import { execFile } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { CONTAINER_IMAGE, DATA_DIR, GROUPS_DIR } from '../../config.js';
import { getAgentGroup } from '../../db/agent-groups.js';
import { restartAgentGroupContainers } from '../../container-restart.js';
import type { CallerContext } from '../frame.js';
import { register } from '../registry.js';

const execute = promisify(execFile);
const root = path.resolve(GROUPS_DIR, '..');
const drafts = path.join(DATA_DIR, '.host-change-drafts');
const hash = (text: string | null) =>
  createHash('sha256')
    .update(text ?? '<absent>')
    .digest('hex');
type Patch = { files: Record<string, string>; tests: string[]; summary: string };
type Draft = Patch & { group: string; baseline: Record<string, string | null>; diff: string; digest: string };

export function sourcePath(value: unknown): string {
  if (
    typeof value !== 'string' ||
    value.includes('..') ||
    value.includes('\\') ||
    !/^(?:src\/(?:cli\/resources|modules\/personal-assistant)|container\/agent-runner\/src\/mcp-tools)\/[a-zA-Z0-9_./-]+\.ts$/.test(
      value,
    )
  )
    throw new Error(
      'Only capability TypeScript source files are supported; config, guards and credentials are excluded.',
    );
  return value;
}

export function parsePatch(args: Record<string, unknown>): Patch {
  if (!args.files || typeof args.files !== 'object' || Array.isArray(args.files)) throw new Error('files is required');
  const files = args.files as Record<string, string>;
  if (!Object.keys(files).length || Object.keys(files).length > 5 || JSON.stringify(files).length > 64000)
    throw new Error('Provide 1–5 source files, at most 64K total; split larger changes.');
  for (const [file, text] of Object.entries(files)) {
    sourcePath(file);
    if (file === 'src/cli/resources/host-changes.ts')
      throw new Error('The host-change approval controller cannot be edited by capability patches.');
    if (typeof text !== 'string' || /[\p{Cf}\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(text))
      throw new Error('Source must be text.');
  }
  if (!Array.isArray(args.tests) || !args.tests.length || args.tests.length > 5)
    throw new Error('Provide 1–5 relevant src test paths.');
  const tests = args.tests.map(sourcePath);
  if (tests.some((test) => !test.startsWith('src/') || !test.endsWith('.test.ts')))
    throw new Error('Tests must be host .test.ts files.');
  if (typeof args.summary !== 'string' || !args.summary.trim() || args.summary.length > 200)
    throw new Error('Provide a summary of at most 200 characters.');
  return { files, tests, summary: args.summary };
}

async function assistant(ctx: CallerContext) {
  if (ctx.caller !== 'agent' || (await getAgentGroup(ctx.agentGroupId))?.folder !== 'personal-assistant')
    throw new Error('Only the Personal Assistant may prepare host capability changes.');
  return ctx;
}

async function readSource(file: string): Promise<string | null> {
  const target = path.join(root, sourcePath(file));
  const parent = await fs.realpath(path.dirname(target));
  if (!parent.startsWith(root + path.sep) || parent !== path.dirname(target))
    throw new Error('Symlinked source paths are rejected.');
  try {
    if ((await fs.lstat(target)).isSymbolicLink()) throw new Error('Symlinked source files are rejected.');
    const text = await fs.readFile(target, 'utf8');
    if (text.length > 64000) throw new Error('Source exceeds 64K.');
    return text;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null;
    throw error;
  }
}

async function snapshot(directory: string) {
  for (const name of ['src', 'container/agent-runner/src', 'package.json', 'tsconfig.json', 'vitest.config.ts']) {
    const target = path.join(directory, name);
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.cp(path.join(root, name), target, { recursive: true });
  }
  await fs.mkdir(path.join(directory, 'node_modules'));
  await execute('git', ['init', '-q', directory]);
  await execute('git', ['-C', directory, 'add', '.']);
}

async function patchDiff(directory: string, files: Record<string, string>) {
  for (const [file, text] of Object.entries(files)) {
    await fs.mkdir(path.dirname(path.join(directory, file)), { recursive: true });
    await fs.writeFile(path.join(directory, file), text);
    await execute('git', ['-C', directory, 'add', '-N', '--', file]);
  }
  const { stdout } = await execute('git', ['-C', directory, 'diff', '--', ...Object.keys(files)]);
  if (!stdout || stdout.length > 1800)
    throw new Error(
      'Patch must be nonempty and fit an exact Telegram approval (1800 characters); split larger changes.',
    );
  return stdout;
}

async function checkPatch(directory: string, tests: string[]) {
  await fs.writeFile(
    path.join(directory, 'check.cjs'),
    'const {execFileSync}=require("node:child_process"); for(const args of [["node_modules/typescript/bin/tsc","--noEmit"],["node_modules/vitest/vitest.mjs","run","--configLoader","runner","--cache=false",...process.argv.slice(2)]]) execFileSync(process.execPath,args,{stdio:"inherit"});',
  );
  await fs.chmod(directory, 0o755);
  const name = `pa-check-${randomUUID()}`;
  try {
    const result = await execute(
      'docker',
      [
        'run',
        '--rm',
        '--name',
        name,
        '--network',
        'none',
        '--read-only',
        '--cap-drop',
        'ALL',
        '--security-opt',
        'no-new-privileges',
        '--pids-limit',
        '128',
        '--memory',
        '2g',
        '--cpus',
        '1',
        '--user',
        `${process.getuid?.() ?? 1000}:${process.getgid?.() ?? 1000}`,
        '--tmpfs',
        '/tmp:rw,nosuid,size=128m',
        '--mount',
        `type=bind,src=${directory},dst=/lab,readonly`,
        '--mount',
        `type=bind,src=${path.join(root, 'node_modules')},dst=/lab/node_modules,readonly`,
        '--workdir',
        '/lab',
        '--entrypoint',
        'node',
        CONTAINER_IMAGE,
        'check.cjs',
        ...tests,
      ],
      { timeout: 120000, maxBuffer: 262144 },
    );
    return { ok: true, stdout: result.stdout.slice(-12000), stderr: result.stderr.slice(-2000) };
  } catch (error) {
    const failure = error as Error & { stdout?: string; stderr?: string };
    const details = [failure.stdout, failure.stderr]
      .filter(Boolean)
      .join('\n')
      .replace(/\x1b\[[0-9;]*m/g, '')
      .slice(-4000);
    throw new Error(
      `Capability checks failed; live source was not changed.\n${details || failure.message.slice(-2000)}`,
      { cause: error },
    );
  } finally {
    await execute('docker', ['rm', '-f', name]).catch(() => undefined);
  }
}

async function stage(args: Patch, ctx: CallerContext) {
  const caller = await assistant(ctx);
  const id = randomUUID();
  const directory = path.join(drafts, id);
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  try {
    const baseline = Object.fromEntries(
      await Promise.all(Object.keys(args.files).map(async (file) => [file, await readSource(file)])),
    );
    const working = path.join(directory, 'source');
    await snapshot(working);
    const diff = await patchDiff(working, args.files);
    const checks = await checkPatch(working, args.tests);
    const digest = hash(JSON.stringify({ files: args.files, baseline }));
    const draft: Draft = { ...args, group: caller.agentGroupId, baseline, diff, digest };
    await fs.writeFile(path.join(directory, 'draft.json'), JSON.stringify(draft), { mode: 0o600 });
    await fs.rm(working, { recursive: true, force: true });
    return {
      id,
      digest,
      diff,
      checks,
      summary: args.summary,
      next: 'Send the diff and checks to the owner, then request host-change-apply with id, digest and this exact diff. Activation and service restart require approval.',
    };
  } catch (error) {
    await fs.rm(directory, { recursive: true, force: true });
    throw error;
  }
}

function parseApproval(args: Record<string, unknown>) {
  if (
    typeof args.id !== 'string' ||
    !/^[a-f0-9-]{36}$/.test(args.id) ||
    typeof args.digest !== 'string' ||
    !/^[a-f0-9]{64}$/.test(args.digest) ||
    typeof args.diff !== 'string' ||
    args.diff.length > 1800
  )
    throw new Error('Provide the tested draft id, digest and exact diff.');
  return { id: args.id, digest: args.digest, diff: args.diff };
}

async function writeFiles(files: Record<string, string | null>) {
  for (const [file, text] of Object.entries(files)) {
    await readSource(file);
    const target = path.join(root, file);
    if (text === null) await fs.rm(target, { force: true });
    else {
      const temporary = `${target}.pa-${randomUUID()}`;
      try {
        await fs.writeFile(temporary, text, { flag: 'wx' });
        await fs.rename(temporary, target);
      } finally {
        await fs.rm(temporary, { force: true });
      }
    }
  }
}

let applying = false;
async function apply(args: ReturnType<typeof parseApproval>, ctx: CallerContext) {
  const caller = await assistant(ctx);
  if (!process.env.INVOCATION_ID) throw new Error('Automatic activation requires a supervised systemd host.');
  if (applying) throw new Error('Another capability activation is running; retry later.');
  applying = true;
  try {
    return await activateDraft(args, caller);
  } finally {
    applying = false;
  }
}

async function activateDraft(
  args: ReturnType<typeof parseApproval>,
  caller: Extract<CallerContext, { caller: 'agent' }>,
) {
  const draft = JSON.parse(await fs.readFile(path.join(drafts, args.id, 'draft.json'), 'utf8')) as Draft;
  if (
    draft.group !== caller.agentGroupId ||
    draft.digest !== args.digest ||
    draft.diff !== args.diff ||
    hash(JSON.stringify({ files: draft.files, baseline: draft.baseline })) !== args.digest
  )
    throw new Error('Approval does not match this immutable tested draft.');
  parsePatch(draft);
  for (const [file, original] of Object.entries(draft.baseline))
    if ((await readSource(file)) !== original)
      throw new Error('Host source changed since testing; prepare a fresh draft.');
  const trial = path.join(drafts, args.id, 'recheck');
  try {
    await snapshot(trial);
    await patchDiff(trial, draft.files);
    await checkPatch(trial, draft.tests);
  } finally {
    await fs.rm(trial, { recursive: true, force: true });
  }
  try {
    await writeFiles(draft.files);
    await execute('node', [path.join(root, 'node_modules/typescript/bin/tsc')], {
      cwd: root,
      timeout: 120000,
      maxBuffer: 262144,
    });
  } catch (error) {
    await writeFiles(draft.baseline);
    await execute('node', [path.join(root, 'node_modules/typescript/bin/tsc')], {
      cwd: root,
      timeout: 120000,
      maxBuffer: 262144,
    });
    throw new Error('Activation failed and the previous source/build was restored.', { cause: error });
  }
  await fs.rename(path.join(drafts, args.id, 'draft.json'), path.join(drafts, args.id, 'applied.json'));
  setTimeout(() => {
    void restartAgentGroupContainers(caller.agentGroupId, 'approved capability patch').finally(() =>
      process.kill(process.pid, 'SIGTERM'),
    );
  }, 10000).unref();
  return { applied: true, id: args.id, summary: draft.summary, host_restart_in_seconds: 10 };
}

register({
  name: 'host-source-read',
  description: 'Read capability source to prepare a precise patch; host config and credentials are excluded.',
  access: 'open',
  parseArgs: (args) => ({ path: sourcePath(args.path) }),
  handler: async (args, ctx) => {
    await assistant(ctx);
    return { path: args.path, source: await readSource(args.path) };
  },
});
register({
  name: 'host-change-stage',
  description: 'Test a small capability patch in an isolated container and prepare an immutable draft.',
  access: 'open',
  parseArgs: parsePatch,
  handler: stage,
});
register({
  name: 'host-change-apply',
  description:
    'Approve the exact tested capability diff, rebuild the host and restart the assistant. Failed builds restore the previous source.',
  access: 'approval',
  parseArgs: parseApproval,
  handler: apply,
});
