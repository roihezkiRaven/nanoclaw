export type CaptureRecord = { groupJid: string; timestamp: string };
export type Coverage = {
  version: 1;
  tracking_since: string;
  connected: boolean;
  heartbeat: string;
  open_gap: string | null;
  gaps: { from: string; until: string }[];
  pruned_gaps: number;
  groups: Record<
    string,
    {
      label: string;
      captured: number;
      uploaded: number;
      first: string | null;
      last: string | null;
      last_upload: string | null;
    }
  >;
  archives: { id: string; modified: string; at: string; groups: string[] }[];
  pruned_archives: number;
  upload_error: string | null;
};

export function initialCoverage(groups: { jid: string; label: string }[], at: string): Coverage {
  return {
    version: 1,
    tracking_since: at,
    connected: false,
    heartbeat: at,
    open_gap: at,
    gaps: [],
    pruned_gaps: 0,
    groups: Object.fromEntries(
      groups.map((g) => [
        g.jid,
        { label: g.label, captured: 0, uploaded: 0, first: null, last: null, last_upload: null },
      ]),
    ),
    archives: [],
    pruned_archives: 0,
    upload_error: null,
  };
}

export function connectionCoverage(state: Coverage, connected: boolean, at: string): void {
  if (!connected) state.open_gap ??= at;
  else if (state.open_gap) {
    state.gaps.push({ from: state.open_gap, until: at });
    state.open_gap = null;
    if (state.gaps.length > 100) {
      state.gaps.shift();
      state.pruned_gaps++;
    }
  }
  state.connected = connected;
  state.heartbeat = at;
}

export function capturedCoverage(state: Coverage, record: CaptureRecord): void {
  const group = state.groups[record.groupJid];
  if (!group) return;
  group.captured++;
  group.first = group.first && group.first < record.timestamp ? group.first : record.timestamp;
  group.last = group.last && group.last > record.timestamp ? group.last : record.timestamp;
}

export function uploadedCoverage(
  state: Coverage,
  records: CaptureRecord[],
  file: { id: string; modifiedTime: string },
  at: string,
): void {
  if (state.archives.some((a) => a.id === file.id)) return;
  const groups = [...new Set(records.map((r) => r.groupJid))];
  state.archives.push({ id: file.id, modified: file.modifiedTime, at, groups });
  // ponytail: retain 10000 archive receipts; pruned history is explicitly unknown, use a durable ledger if full history is required.
  if (state.archives.length > 10000) {
    state.archives.shift();
    state.pruned_archives++;
  }
  for (const record of records) {
    const group = state.groups[record.groupJid];
    if (group) {
      group.uploaded++;
      group.last_upload = at;
    }
  }
  state.upload_error = null;
}

export function ingestionCoverage(
  state: Coverage,
  checkpoint: {
    updated?: string;
    sources?: Record<string, { modified?: string }>;
    files?: Record<string, { modifiedTime?: string }>;
  },
  now = Date.now(),
) {
  const pending = state.archives.filter(
    (a) => (checkpoint.files?.[a.id]?.modifiedTime ?? checkpoint.sources?.[a.id]?.modified) !== a.modified,
  );
  return {
    tracking_since: state.tracking_since,
    complete_capture_verified: false,
    historical_backlog: 'unknown before tracking or outside retained ledger',
    ledger_pruned: state.pruned_archives,
    ingestion_status: !checkpoint.updated
      ? 'unverified'
      : now - Date.parse(checkpoint.updated) > 26 * 3600000
        ? 'stale'
        : pending.length
          ? 'pending'
          : 'caught_up_for_retained_ledger',
    capture_status:
      state.connected && now - Date.parse(state.heartbeat) < 90000
        ? 'connected_with_unknown_gaps'
        : 'disconnected_or_stale',
    checkpoint_at: checkpoint.updated ?? null,
    checkpoint_age_seconds: checkpoint.updated ? (now - Date.parse(checkpoint.updated)) / 1000 : null,
    observed_unprocessed_archives: pending.length,
    oldest_unprocessed_at: pending[0]?.at ?? null,
    groups: Object.entries(state.groups).map(([jid, g]) => ({
      jid,
      ...g,
      coverage: 'unverified',
      observed_unprocessed_archives: pending.filter((a) => a.groups.includes(jid)).length,
    })),
    connected: state.connected,
    heartbeat: state.heartbeat,
    open_gap: state.open_gap,
    possible_capture_gaps: state.gaps,
    pruned_gaps: state.pruned_gaps,
    upload_error: state.upload_error,
  };
}
