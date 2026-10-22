import { getPendingApproval, getSession } from '../../db/sessions.js';
import { retryApprovalDelivery } from '../../modules/approvals/primitive.js';
import { register } from '../registry.js';
import { registerResource } from '../crud.js';

registerResource({
  name: 'approval',
  plural: 'approvals',
  table: 'pending_approvals',
  description:
    'Pending approval — in-flight approval cards waiting for an admin response. Created by requestApproval() (self-mod install_packages/add_mcp_server) and OneCLI credential approval flow. Rows are deleted after the admin approves/rejects or the request expires.',
  idColumn: 'approval_id',
  columns: [
    {
      name: 'approval_id',
      type: 'string',
      description: 'Unique approval identifier (also used as the card questionId).',
    },
    {
      name: 'session_id',
      type: 'string',
      description: 'Session that requested the approval. Null for OneCLI credential approvals.',
    },
    {
      name: 'request_id',
      type: 'string',
      description: 'Original request identifier (OneCLI request UUID or same as approval_id).',
    },
    {
      name: 'action',
      type: 'string',
      description:
        'Action type — matches the registered approval handler (e.g. install_packages, add_mcp_server, onecli_credential).',
    },
    { name: 'payload', type: 'json', description: 'JSON payload carried through to the approval handler.' },
    { name: 'created_at', type: 'string', description: 'Auto-set.' },
    { name: 'agent_group_id', type: 'string', description: 'Originating agent group.' },
    { name: 'channel_type', type: 'string', description: 'Channel the approval card was delivered on.' },
    { name: 'platform_id', type: 'string', description: 'Platform chat ID the card was delivered to.' },
    {
      name: 'platform_message_id',
      type: 'string',
      description: 'Platform message ID of the delivered card (for editing on expiry).',
    },
    { name: 'expires_at', type: 'string', description: 'When this approval expires (OneCLI gateway TTL).' },
    {
      name: 'status',
      type: 'string',
      description: 'Current status.',
      enum: ['pending', 'approved', 'rejected', 'expired'],
    },
    { name: 'title', type: 'string', description: 'Card title shown to the admin.' },
    { name: 'options_json', type: 'json', description: 'Card button options as JSON array.' },
  ],
  operations: { list: 'open', get: 'open' },
});

register({
  name: 'approval-delivery-retry',
  access: 'open',
  description: 'Retry delivery of your own pending approval card; never executes or approves the action.',
  parseArgs: (args) => {
    if (typeof args.id !== 'string') throw new Error('id is required');
    return { id: args.id };
  },
  handler: async (args, ctx) => {
    const row = await getPendingApproval(args.id);
    const group = row?.agent_group_id ?? (row?.session_id ? (await getSession(row.session_id))?.agent_group_id : null);
    if (!row || (ctx.caller === 'agent' && group !== ctx.agentGroupId)) throw new Error('Approval not found');
    return { approval_id: args.id, delivery: await retryApprovalDelivery(args.id), action_executed: false };
  },
});
