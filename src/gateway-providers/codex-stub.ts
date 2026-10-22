import fs from 'node:fs';
import path from 'node:path';

/** Fix OneCLI #577 using workspace metadata; bearer credentials remain placeholders. */
export function repairCodexStub(dataDir: string, groupId: string, content: string): string {
  const stub = JSON.parse(content);
  if (stub.auth_mode !== 'chatgpt' || stub.tokens?.account_id !== 'onecli-managed') return content;
  const identity = readCodexIdentity(dataDir, groupId);
  if (!identity) return content;
  if (stub.tokens.access_token !== 'onecli-managed' || stub.tokens.refresh_token !== 'onecli-managed') {
    throw new Error('Codex workspace repair requires placeholder credentials');
  }
  return stampCodexIdentity(stub, identity);
}

function readCodexIdentity(dataDir: string, groupId: string): { account_id: string; plan_type?: string } | undefined {
  if (!/^[a-zA-Z0-9_-]+$/.test(groupId)) throw new Error('Invalid Codex group id');
  let identity;
  try {
    identity = JSON.parse(fs.readFileSync(path.join(dataDir, 'onecli', `${groupId}-codex-identity.json`), 'utf8'));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined;
    throw error;
  }
  if (typeof identity.account_id !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(identity.account_id)) {
    throw new Error('Invalid Codex workspace id');
  }
  return identity;
}

function stampCodexIdentity(
  stub: { tokens: { id_token: string; account_id: string } },
  identity: { account_id: string; plan_type?: string },
): string {
  const parts = stub.tokens.id_token.split('.');
  if (parts.length !== 3) throw new Error('Invalid Codex identity stub');
  const claims = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
  const auth = claims['https://api.openai.com/auth'];
  auth.chatgpt_account_id = identity.account_id;
  if (typeof identity.plan_type === 'string') auth.chatgpt_plan_type = identity.plan_type;
  else delete auth.chatgpt_plan_type;
  parts[1] = Buffer.from(JSON.stringify(claims)).toString('base64url');
  stub.tokens.id_token = parts.join('.');
  stub.tokens.account_id = identity.account_id;
  return JSON.stringify(stub);
}
