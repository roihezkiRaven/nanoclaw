#!/usr/bin/env node
/** Read-only drift check for the deployable personal fork. */
import { execFileSync } from 'node:child_process';
import path from 'node:path';

function git(root: string, args: string[]): string {
  return execFileSync('git', ['-C', root, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

function main(): void {
  const root = path.resolve(process.argv[2] || process.cwd());
  const local = git(root, ['rev-parse', 'HEAD']);
  const remote = git(root, ['ls-remote', '--heads', 'origin', 'main']).split(/\s+/)[0];
  if (!/^[0-9a-f]{40}$/.test(local) || !/^[0-9a-f]{40}$/.test(remote)) {
    throw new Error('origin/main or HEAD is unavailable');
  }
  console.log(
    JSON.stringify({
      root,
      currentCommit: local,
      availableCommit: remote,
      updateAvailable: local !== remote,
      checkedAt: new Date().toISOString(),
    }),
  );
}

main();
