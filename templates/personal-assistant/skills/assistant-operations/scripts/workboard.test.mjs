import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pa-work-test-'));
const script = new URL('./workboard.mjs', import.meta.url).pathname;
const run = (...args) => JSON.parse(execFileSync('node', [script, ...args], { env: { ...process.env, PA_WORKSPACE: root }, stdio: ['ignore', 'pipe', 'pipe'] }));
try {
  run('refine', 'Deliver artifacts before status', 'owner test');
  assert.equal(run('preferences').preferences[0].text, 'Deliver artifacts before status');
  assert.throws(() => run('put', '../escape', '{}'));
  assert.throws(() => run('put', 'fake', JSON.stringify({ kind: 'commitment', title: 'Unapproved', status: 'active' })));
  run('put', 'real', JSON.stringify({ kind: 'project', title: 'Deliver', status: 'active', next_action: 'Build' }));
  run('put', 'real', JSON.stringify({ next_action: 'Review' }));
  assert.equal(run('get', 'real').title, 'Deliver');
  run('capability', 'trial', 'candidate', JSON.stringify({ failure: 'Observed error', procedure: 'Check dates', cases: ['valid', 'stale'] }));
  assert.throws(() => run('capability', 'trial', 'promote', '1'));
  run('capability', 'trial', 'evaluate', JSON.stringify({ ok: true, baseline_compared: true, evidence: 'labs/trial/result.json' }));
  assert.throws(() => run('capability', 'trial', 'promote', '1'));
  fs.mkdirSync(path.join(root, 'labs/trial'), { recursive: true });
  fs.writeFileSync(path.join(root, 'labs/trial/result.json'), JSON.stringify({ ok: true, baseline_compared: true, cases: [{ name: 'valid', pass: true }, { name: 'stale', pass: true }] }));
  run('capability', 'trial', 'promote', '1');
  assert.equal(run('preferences').capabilities.trial.active, 1);
  run('capability', 'trial', 'monitor', 'failure');
  assert.equal(run('preferences').capabilities.trial.active, null);
  console.log('PASS: persistence across processes, path rejection, explicit commitments, non-destructive update, promotion gate, regression rollback');
} finally { fs.rmSync(root, { recursive: true, force: true }); }
