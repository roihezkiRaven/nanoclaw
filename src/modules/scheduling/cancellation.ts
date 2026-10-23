import fs from 'node:fs';
import path from 'node:path';
import { DATA_DIR } from '../../config.js';

function marker(session: string): string {
  if (!/^[a-zA-Z0-9-]+$/.test(session)) throw new Error('Invalid task session');
  return path.join(DATA_DIR, '.task-cancellations', session);
}

export function taskSessionCancelled(session: string): boolean {
  return fs.existsSync(marker(session));
}

/** Host-owned tombstone survives completed-row/rearm races and host restarts. */
export function cancelTaskSession(session: string): void {
  const file = marker(session);
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.writeFileSync(file, new Date().toISOString(), { mode: 0o600 });
  for (const target of [file, path.dirname(file), DATA_DIR]) {
    const descriptor = fs.openSync(target, 'r');
    try {
      fs.fsyncSync(descriptor);
    } finally {
      fs.closeSync(descriptor);
    }
  }
}
