/** Small capability patches: isolated checks, immutable draft, exact owner approval. */
import { execFile } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { CONTAINER_IMAGE, DATA_DIR, GROUPS_DIR } from '../../config.js';
import { getAgentGroup } from '../../db/agent-groups.js';
import { INSTALL_SLUG } from '../../config.js';
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
type Draft = Patch & {
  format?: number;
  group: string;
  baseline: Record<string, string | null>;
  diff: string;
  digest: string;
};

export function sourcePath(value: unknown): string {
  if (
    typeof value !== 'string' ||
    value.includes('..') ||
    value.includes('\\') ||
    !(
      /^(?:src\/(?:cli\/resources|modules\/(?:personal-assistant|scheduling))|container\/agent-runner\/src\/mcp-tools)\/[a-zA-Z0-9_./-]+\.ts$/.test(
        value,
      ) ||
      /^(?:tools\/(?:gdrive_(?:broker|assistant)(?:_test)?\.py|whatsapp_collector\.ts)|src\/(?:delivery|model-catalog|cli\/format-tasks|mailbox\/types|mailbox\/sqlite\/tasks)(?:\.test)?\.ts)$/.test(
        value,
      )
    )
  )
    throw new Error(
      'Only allowlisted integration source and tests are supported; controllers, config, guards and credentials are excluded.',
    );
  return value;
}

function invalidSourceText(text: string): boolean {
  for (const char of text) {
    const code = char.codePointAt(0)!;
    if (/\p{Cf}/u.test(char) || (code < 32 && ![9, 10, 13].includes(code)) || code === 127) return true;
  }
  return false;
}

export function parsePatch(args: Record<string, unknown>): Patch {
  if (!args.files || typeof args.files !== 'object' || Array.isArray(args.files)) throw new Error('files is required');
  const files = args.files as Record<string, string>;
  if (
    !Object.keys(files).length ||
    Object.keys(files).length > 20 ||
    Buffer.byteLength(JSON.stringify(files)) > 512 * 1024
  )
    throw new Error('Provide 1–20 source files, at most 512 KiB total.');
  for (const [file, text] of Object.entries(files)) {
    sourcePath(file);
    if (file === 'src/cli/resources/host-changes.ts')
      throw new Error('The host-change approval controller cannot be edited by capability patches.');
    if (typeof text !== 'string' || invalidSourceText(text)) throw new Error('Source must be text.');
  }
  if (!Array.isArray(args.tests) || !args.tests.length || args.tests.length > 10)
    throw new Error('Provide 1–10 relevant TypeScript/Python test paths.');
  const tests = args.tests.map(sourcePath);
  if (
    tests.some(
      (test) =>
        !(test.startsWith('src/') && test.endsWith('.test.ts')) &&
        !/^tools\/gdrive_(?:broker|assistant)_test\.py$/.test(test),
    )
  )
    throw new Error('Tests must be allowlisted host .test.ts or integration _test.py files.');
  if (
    typeof args.summary !== 'string' ||
    !args.summary.trim() ||
    invalidSourceText(args.summary) ||
    args.summary.length > 200
  )
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
    if (Buffer.byteLength(text) > 512 * 1024) throw new Error('Source exceeds 512 KiB.');
    return text;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null;
    throw error;
  }
}

async function snapshot(directory: string) {
  for (const name of [
    'src',
    'tools',
    'container/agent-runner/src',
    'package.json',
    'tsconfig.json',
    'vitest.config.ts',
  ]) {
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
  if (!stdout || Buffer.byteLength(stdout) > 512 * 1024)
    throw new Error(
      'Patch must be nonempty and at most 512 KiB; full immutable review is available before exact-digest approval.',
    );
  return stdout;
}

async function isolatedCheck(directory: string, image: string, command: string[]) {
  const name = `pa-check-${randomUUID()}`;
  try {
    return await execute(
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
        command[0],
        image,
        ...command.slice(1),
      ],
      { timeout: 120000, maxBuffer: 262144 },
    );
  } finally {
    await execute('docker', ['rm', '-f', name]).catch(() => undefined);
  }
}

async function checkPatch(directory: string, tests: string[]) {
  const ts = tests.filter((t) => t.endsWith('.test.ts'));
  const py = tests.filter((t) => t.endsWith('_test.py'));
  await fs.writeFile(
    path.join(directory, 'check.cjs'),
    'const {execFileSync}=require("node:child_process"); const checks=[["node_modules/typescript/bin/tsc","--noEmit"]]; if(process.argv.length>2)checks.push(["node_modules/vitest/vitest.mjs","run","--configLoader","runner","--cache=false",...process.argv.slice(2)]);for(const args of checks)execFileSync(process.execPath,args,{stdio:"inherit"});',
  );
  await fs.chmod(directory, 0o755);
  try {
    const results = [await isolatedCheck(directory, CONTAINER_IMAGE, ['node', 'check.cjs', ...ts])];
    if (py.length)
      results.push(
        await isolatedCheck(directory, 'nanoclaw-maintenance-python:3.13', [
          'python',
          '-B',
          '-m',
          'unittest',
          ...py.map((t) => t.replaceAll('/', '.').slice(0, -3)),
        ]),
      );
    return {
      ok: true,
      stdout: results
        .map((r) => r.stdout)
        .join('\n')
        .slice(-16000),
      stderr: results
        .map((r) => r.stderr)
        .join('\n')
        .slice(-4000),
    };
  } catch (error) {
    const failure = error as Error & { stdout?: string; stderr?: string };
    throw new Error(
      `Capability checks failed; live source unchanged.\n${[failure.stdout, failure.stderr].filter(Boolean).join('\n').slice(-4000)}`,
      { cause: error },
    );
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
    const digest = hash(JSON.stringify({ files: args.files, baseline, tests: args.tests, summary: args.summary }));
    const draft: Draft = { ...args, format: 2, group: caller.agentGroupId, baseline, diff, digest };
    await fs.writeFile(path.join(directory, 'draft.json'), JSON.stringify(draft), { mode: 0o600 });
    await fs.rm(working, { recursive: true, force: true });
    return {
      id,
      digest,
      diff: diff.length <= 1800 ? diff : undefined,
      diff_sha256: hash(diff),
      review: `ncl host-change-review --id ${id} --offset 0`,
      checks,
      summary: args.summary,
      paths: Object.keys(args.files).sort(),
      next: 'Read the complete immutable diff with host-change-review; request native approval with id, digest and diff_sha256. Activation is healthy only after independent restart checks.',
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
    !(
      (typeof args.diff === 'string' && args.diff.length <= 1800) ||
      (typeof args.diff_sha256 === 'string' && /^[a-f0-9]{64}$/.test(args.diff_sha256))
    )
  )
    throw new Error('Provide immutable draft id, digest and exact diff or diff_sha256.');
  if (
    args.diff === undefined &&
    (typeof args.summary !== 'string' ||
      !args.summary.trim() ||
      invalidSourceText(args.summary) ||
      args.summary.length > 200 ||
      !Array.isArray(args.paths) ||
      args.paths.length < 1 ||
      args.paths.length > 20 ||
      args.paths.some((p) => typeof p !== 'string'))
  )
    throw new Error('Digest approval also requires the exact tested summary and changed paths for the review card');
  return {
    id: args.id,
    digest: args.digest,
    diff: args.diff as string | undefined,
    diff_sha256: args.diff_sha256 as string | undefined,
    summary: args.summary as string | undefined,
    paths: args.paths as string[] | undefined,
  };
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
    (args.diff !== undefined ? draft.diff !== args.diff : hash(draft.diff) !== args.diff_sha256) ||
    hash(
      JSON.stringify(
        draft.format === 2
          ? { files: draft.files, baseline: draft.baseline, tests: draft.tests, summary: draft.summary }
          : { files: draft.files, baseline: draft.baseline },
      ),
    ) !== args.digest
  )
    throw new Error('Approval does not match this immutable tested draft.');
  if (
    args.diff === undefined &&
    (args.summary !== draft.summary ||
      JSON.stringify([...(args.paths ?? [])].sort()) !== JSON.stringify(Object.keys(draft.files).sort()))
  )
    throw new Error('Approval summary or paths differ from the tested immutable draft');
  try {
    const activation = JSON.parse(await fs.readFile(path.join(drafts, args.id, 'activation.json'), 'utf8'));
    if (activation.state) throw new Error('Draft already activated or attempted; stage a fresh draft');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }
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
  await fs.mkdir(path.join(drafts, '.activation-lock'));
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
    await fs.rmdir(path.join(drafts, '.activation-lock'));
    throw new Error('Activation failed and the previous source/build was restored.', { cause: error });
  }
  const directory = path.join(drafts, args.id);
  const unit = `nanoclaw-v2-${INSTALL_SLUG}.service`;
  await fs.writeFile(
    path.join(directory, 'activation.json'),
    JSON.stringify({
      state: 'built',
      checked_at: new Date().toISOString(),
      unit,
      group: caller.agentGroupId,
      baseline: draft.baseline,
      candidate: draft.files,
      old_pid: process.pid,
    }),
    { mode: 0o600 },
  );
  try {
    await execute('systemd-run', [
      '--user',
      '--collect',
      '--unit',
      `pa-maintenance-${args.id}`,
      '--property=Type=exec',
      'python3',
      path.join(root, 'tools/maintenance_supervisor.py'),
      root,
      args.id,
    ]);
  } catch (error) {
    await writeFiles(draft.baseline);
    await execute('node', [path.join(root, 'node_modules/typescript/bin/tsc')], { cwd: root, timeout: 120000 });
    await fs.rmdir(path.join(drafts, '.activation-lock'));
    throw new Error('Restart supervisor could not start; previous source/build restored.', { cause: error });
  }
  return {
    id: args.id,
    state: 'built',
    healthy: false,
    next: 'Independent supervisor will restart, smoke-test and roll back on failure. Read host-change-status for actual activation state.',
  };
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

register({
  name: 'host-change-review',
  access: 'open',
  description: 'Read the immutable full tested diff in chunks before digest approval.',
  parseArgs: (args) => {
    if (
      typeof args.id !== 'string' ||
      !/^[a-f0-9-]{36}$/.test(args.id) ||
      (args.offset !== undefined &&
        ((typeof args.offset !== 'string' && typeof args.offset !== 'number') ||
          !Number.isSafeInteger(Number(args.offset)) ||
          Number(args.offset) < 0))
    )
      throw new Error('Invalid draft id/offset');
    return { id: args.id, offset: Number(args.offset ?? 0) };
  },
  handler: async (args, ctx) => {
    const caller = await assistant(ctx);
    const draft: Draft = JSON.parse(await fs.readFile(path.join(drafts, args.id, 'draft.json'), 'utf8'));
    if (draft.group !== caller.agentGroupId) throw new Error('Draft not found');
    if (args.offset > draft.diff.length) throw new Error('offset exceeds diff length');
    const end = Math.min(args.offset + 16000, draft.diff.length);
    return {
      id: args.id,
      digest: draft.digest,
      diff_sha256: hash(draft.diff),
      summary: draft.summary,
      tests: draft.tests,
      offset: args.offset,
      diff: draft.diff.slice(args.offset, end),
      next_offset: end < draft.diff.length ? end : null,
    };
  },
});
register({
  name: 'host-change-status',
  access: 'open',
  description: 'Read actual restart/health/rollback state, not draft success.',
  parseArgs: (args) => {
    if (typeof args.id !== 'string' || !/^[a-f0-9-]{36}$/.test(args.id)) throw new Error('Invalid draft id');
    return { id: args.id };
  },
  handler: async (args, ctx) => {
    const caller = await assistant(ctx);
    const draft: Draft = JSON.parse(await fs.readFile(path.join(drafts, args.id, 'draft.json'), 'utf8'));
    if (draft.group !== caller.agentGroupId) throw new Error('Draft not found');
    try {
      const value = JSON.parse(await fs.readFile(path.join(drafts, args.id, 'activation.json'), 'utf8'));
      return {
        id: args.id,
        state: value.state,
        healthy: value.state === 'healthy',
        checked_at: value.checked_at,
        error: value.error ?? null,
      };
    } catch (error) {
      return {
        id: args.id,
        state: (error as NodeJS.ErrnoException).code === 'ENOENT' ? 'staged' : 'unavailable',
        healthy: false,
      };
    }
  },
});
