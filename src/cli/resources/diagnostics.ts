import { execFile } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { DATA_DIR, GROUPS_DIR, INSTALL_SLUG } from '../../config.js';
import { getAgentGroup } from '../../db/agent-groups.js';
import { getDb } from '../../db/connection.js';
import { ingestionCoverage, type Coverage } from '../../modules/personal-assistant/whatsapp-coverage.js';
import { register } from '../registry.js';

const execute = promisify(execFile);

export async function diagnosticJson<T = unknown>(
  file: string,
): Promise<{ value?: T; modified_at?: string; status: string }> {
  try {
    const stat = await fs.stat(file);
    if (stat.size > 4 * 1024 * 1024) return { status: 'too_large' };
    return {
      value: JSON.parse(await fs.readFile(file, 'utf8')),
      modified_at: stat.mtime.toISOString(),
      status: 'available',
    };
  } catch {
    return { status: 'unavailable' };
  }
}

async function serviceHealth(unit: string) {
  try {
    const { stdout } = await execute('systemctl', ['--user', 'is-active', unit], { timeout: 3000 });
    return { unit, status: stdout.trim() };
  } catch {
    return { unit, status: 'inactive_or_unavailable' };
  }
}

async function whatsappDiagnostics(root: string) {
  const [coverage, checkpoint] = await Promise.all([
    diagnosticJson<Coverage>(path.join(root, 'store/whatsapp-collector/coverage.json')),
    diagnosticJson<{
      updated?: string;
      sources?: Record<string, { modified?: string }>;
      files?: Record<string, { modifiedTime?: string }>;
    }>(path.join(DATA_DIR, 'timeless-wiki/whatsapp-ingestion.json')),
  ]);
  if (coverage.status !== 'available' || checkpoint.status !== 'available')
    return {
      status: 'unavailable',
      coverage: coverage.status,
      ingestion_checkpoint: checkpoint.status,
      complete_capture_verified: false,
    };
  try {
    return {
      status: 'available',
      ...ingestionCoverage(coverage.value as Coverage, {
        ...checkpoint.value,
        updated: checkpoint.value?.updated ?? checkpoint.modified_at,
      }),
    };
  } catch {
    return { status: 'invalid_checkpoint', complete_capture_verified: false };
  }
}

register({
  name: 'assistant-diagnostics',
  access: 'open',
  description:
    'Read service health, your pending approval delivery, work/evidence freshness and WhatsApp ingestion lag. Does not repair, send messages or expose secrets.',
  parseArgs: (args) => ({ group: typeof args.group === 'string' ? args.group : undefined }),
  handler: async (args, ctx) => {
    const groupId = ctx.caller === 'agent' ? ctx.agentGroupId : args.group;
    if (!groupId) throw new Error('--group is required for operator diagnostics');
    const group = await getAgentGroup(groupId);
    if (group?.folder !== 'personal-assistant') throw new Error('Personal Assistant only');
    const root = path.resolve(GROUPS_DIR, '..');
    const [services, state, whatsapp, approvals] = await Promise.all([
      Promise.all(
        [`nanoclaw-v2-${INSTALL_SLUG}.service`, 'gdrive-broker.service', 'whatsapp-collector.service'].map(
          serviceHealth,
        ),
      ),
      diagnosticJson<{
        records?: Record<
          string,
          { id: string; status: string; verified_at?: string; evidence?: string; review_at?: string }
        >;
      }>(path.join(GROUPS_DIR, group.folder, 'work/state.json')),
      whatsappDiagnostics(root),
      getDb().all<{
        approval_id: string;
        action: string;
        status: string;
        created_at: string;
        platform_message_id: string | null;
        payload: string;
      }>(
        'SELECT p.approval_id,p.action,p.status,p.created_at,p.platform_message_id,p.payload FROM pending_approvals p LEFT JOIN sessions s ON s.id=p.session_id WHERE p.agent_group_id=? OR s.agent_group_id=?',
        groupId,
        groupId,
      ),
    ]);
    return {
      checked_at: new Date().toISOString(),
      services,
      whatsapp,
      approvals: approvals.map(({ payload, ...row }) => {
        let delivery = 'unverified';
        try {
          delivery = JSON.parse(payload).delivery?.status ?? (row.platform_message_id ? 'delivered' : 'unverified');
        } catch {
          /* No payload contents are exposed. */
        }
        return { ...row, delivery };
      }),
      recent_failures: [
        ...services
          .filter((service) => service.status !== 'active')
          .map((service) => ({ component: service.unit, status: service.status })),
        ...approvals
          .filter((row) => {
            try {
              return ['failed', 'unavailable'].includes(JSON.parse(row.payload).delivery?.status);
            } catch {
              return false;
            }
          })
          .map((row) => ({
            component: 'approval-card',
            status: 'delivery_failed_or_unavailable',
            id: row.approval_id,
          })),
        ...('upload_error' in whatsapp && whatsapp.upload_error
          ? [{ component: 'whatsapp-upload', status: 'failed' }]
          : []),
      ],
      work_status: state.status,
      work_modified_at: state.modified_at ?? null,
      records: Object.values(state.value?.records ?? {}).map((r) => ({
        id: r.id,
        status: r.status,
        verified_at: r.verified_at ?? null,
        evidence: r.evidence ?? null,
        evidence_age_seconds:
          r.verified_at && Number.isFinite(Date.parse(r.verified_at))
            ? (Date.now() - Date.parse(r.verified_at)) / 1000
            : null,
        source: 'workspace_record',
        overdue_review: r.review_at ? Date.parse(r.review_at) < Date.now() : null,
      })),
    };
  },
});
