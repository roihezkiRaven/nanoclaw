export interface TaskContent {
  timezone?: string;
  prompt: string;
  script: string | null;
  originSessionId: string | null;
}

/** Decode the storage-neutral task content envelope. */
export function parseTaskContent(raw: string): TaskContent {
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return {
      ...(typeof parsed.timezone === 'string' ? { timezone: parsed.timezone } : {}),
      prompt: typeof parsed.prompt === 'string' ? parsed.prompt : '',
      script: typeof parsed.script === 'string' ? parsed.script : null,
      originSessionId: typeof parsed.originSessionId === 'string' ? parsed.originSessionId : null,
    };
    // eslint-disable-next-line no-catch-all/no-catch-all -- LEGACY-COMPAT(v1-tasks): plain-string content predating the JSON envelope
  } catch {
    return { prompt: raw, script: null, originSessionId: null };
  }
}

/** Validate an explicitly selected IANA timezone; null restores group default. */
export function taskTimezone(value: unknown): string | null | undefined {
  if (value === undefined) return undefined;
  if (value === null || value === 'none' || value === 'null') return null;
  if (typeof value !== 'string' || !value.trim()) throw new Error('timezone must be an IANA name');
  try {
    new Intl.DateTimeFormat('en', { timeZone: value });
  } catch (error) {
    throw new Error('timezone must be a valid IANA name', { cause: error });
  }
  return value;
}
