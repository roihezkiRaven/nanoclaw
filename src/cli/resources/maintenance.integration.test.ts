import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { expect, it, vi } from 'vitest';
vi.mock('../../db/agent-groups.js', () => ({ getAgentGroup: async () => ({ folder: 'personal-assistant' }) }));
import './host-changes.js';
import { lookup } from '../registry.js';

const integration = process.env.PA_MAINTENANCE_INTEGRATION === '1' ? it : it.skip;
const ctx = { caller: 'agent' as const, agentGroupId: 'fixture', sessionId: 'fixture', messagingGroupId: 'fixture' };

integration(
  'stages and reviews a large patch in real offline containers without modifying source',
  async () => {
    const file = 'src/modules/personal-assistant/maintenance-fixture.ts';
    const test = 'src/modules/personal-assistant/maintenance-fixture.test.ts';
    const stage = lookup('host-change-stage')!;
    const result = (await stage.handler(
      stage.parseArgs({
        summary: 'Integration fixture only',
        files: {
          [file]: 'export const fixture = 7;\n' + '// bounded fixture\n'.repeat(200),
          [test]:
            "import {expect,it} from 'vitest';import {fixture} from './maintenance-fixture.js';it('fixture',()=>expect(fixture).toBe(7));\n",
        },
        tests: [test],
      }),
      ctx,
    )) as any;
    expect(result.checks.ok).toBe(true);
    expect(result.diff).toBeUndefined();
    const review = lookup('host-change-review')!;
    let content = '';
    let offset: number | null = 0;
    while (offset !== null) {
      const chunk = (await review.handler(review.parseArgs({ id: result.id, offset }), ctx)) as any;
      content += chunk.diff;
      offset = chunk.next_offset;
    }
    expect(createHash('sha256').update(content).digest('hex')).toBe(result.diff_sha256);
    await expect(fs.stat(path.resolve(file))).rejects.toThrow();
    await expect(
      review.handler(review.parseArgs({ id: result.id }), { ...ctx, agentGroupId: 'foreign' }),
    ).rejects.toThrow('Draft not found');
  },
  180000,
);

integration(
  'validates the actual Python integration in an offline Python runner',
  async () => {
    const source = await fs.readFile('tools/gdrive_broker.py', 'utf8');
    const stage = lookup('host-change-stage')!;
    const result = (await stage.handler(
      stage.parseArgs({
        files: { 'tools/gdrive_broker.py': source + '\n# fixture only\n' },
        tests: ['tools/gdrive_broker_test.py'],
        summary: 'Python fixture only',
      }),
      ctx,
    )) as any;
    expect(result.checks.ok).toBe(true);
    expect(await fs.readFile('tools/gdrive_broker.py', 'utf8')).toBe(source);
  },
  180000,
);
