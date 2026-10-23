import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, expect, it } from 'vitest';

import { repairCodexStub } from './codex-stub.js';

let dir: string;
const claims = { 'https://api.openai.com/auth': { chatgpt_account_id: 'onecli-managed', chatgpt_plan_type: 'free' } };
const content = JSON.stringify({
  auth_mode: 'chatgpt',
  tokens: {
    account_id: 'onecli-managed',
    access_token: 'onecli-managed',
    refresh_token: 'onecli-managed',
    id_token: `e30.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.`,
  },
});

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-stub-'));
  fs.mkdirSync(path.join(dir, 'onecli'));
  fs.writeFileSync(
    path.join(dir, 'onecli', 'ag-test-codex-identity.json'),
    JSON.stringify({ account_id: 'workspace-123', plan_type: 'pro' }),
  );
});
afterEach(() => fs.rmSync(dir, { recursive: true, force: true }));

it('repairs workspace and plan claims while keeping bearer and refresh credentials placeholders', () => {
  const stub = JSON.parse(repairCodexStub(dir, 'ag-test', content));
  const auth = JSON.parse(Buffer.from(stub.tokens.id_token.split('.')[1], 'base64url').toString())[
    'https://api.openai.com/auth'
  ];
  expect(stub.tokens.account_id).toBe('workspace-123');
  expect(auth).toEqual({ chatgpt_account_id: 'workspace-123', chatgpt_plan_type: 'pro' });
  expect(stub.tokens.access_token).toBe('onecli-managed');
  expect(stub.tokens.refresh_token).toBe('onecli-managed');
});

it('preserves the gateway stub when no identity metadata has been configured', () => {
  expect(repairCodexStub(dir, 'ag-other', content)).toBe(content);
});

it('refuses invalid identity metadata and unexpected credential contents', () => {
  const stub = JSON.parse(content);
  stub.tokens.access_token = 'unexpected';
  expect(() => repairCodexStub(dir, 'ag-test', JSON.stringify(stub))).toThrow('placeholder credentials');
  fs.writeFileSync(path.join(dir, 'onecli', 'ag-test-codex-identity.json'), '{"account_id":"../bad"}');
  expect(() => repairCodexStub(dir, 'ag-test', content)).toThrow('Invalid Codex workspace id');
});
