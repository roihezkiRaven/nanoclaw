/** Match bounded host operations; ordinary CLI requests still fail promptly. */
export function commandTimeoutMs(command: string): number {
  if (command === 'agy-media-run') return 18 * 60_000;
  if (command === 'agy-run') return 6 * 60_000;
  if (command === 'host-change-stage' || command === 'host-change-apply') return 5 * 60_000;
  return 30_000;
}
