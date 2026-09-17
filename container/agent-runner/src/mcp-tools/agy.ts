/** Explicit NanoClaw tool for delegating a bounded request to host-side agy. */
import { registerTools } from './server.js';
import type { McpToolDefinition } from './types.js';

const MODEL_RE = /^(?:gemini|claude|gpt-oss)-[a-z0-9][a-z0-9._-]{0,79}$/i;
const AGY_MODELS = new Set([
  'gemini-3.8-flash-high',
  'gemini-3.8-flash-medium',
  'gemini-3.8-flash-low',
  'gemini-3.7-flash-high',
  'gemini-3.7-flash-medium',
  'gemini-3.7-flash-low',
  'gemini-3.6-flash-high',
  'gemini-3.6-flash-medium',
  'gemini-3.6-flash-low',
  'gemini-3.1-pro-high',
  'gemini-3.1-pro-low',
]);
const EFFORTS = new Set(['low', 'medium', 'high']);
const MAX_PROMPT_CHARS = 24_000;

function ok(text: string) {
  return { content: [{ type: 'text' as const, text }] };
}

function err(text: string) {
  return { content: [{ type: 'text' as const, text: `Error: ${text}` }], isError: true };
}

function generateId(): string {
  return `agy-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runNcl(args: Record<string, unknown>): Promise<string> {
  const child = Bun.spawn(['/usr/local/bin/ncl', 'agy-run', '--stdin-json', '--json'], {
    stdin: 'pipe',
    stdout: 'pipe',
    stderr: 'pipe',
  });
  child.stdin.write(JSON.stringify(args));
  child.stdin.end();
  const [stdout, stderr, code] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited,
  ]);
  if (code !== 0) throw new Error(stderr.trim() || `ncl exited with code ${code}`);
  return stdout;
}

export const runAgy: McpToolDefinition = {
  tool: {
    name: 'run_agy',
    description:
      'Delegate one bounded, read-only research or transformation request to the owner-authenticated Antigravity CLI. The request is sent to Google; NanoClaw files and credentials are not mounted. Use for analysis, summaries, and drafting—not direct system changes.',
    inputSchema: {
      type: 'object' as const,
      properties: {
        prompt: { type: 'string', description: `Task prompt (maximum ${MAX_PROMPT_CHARS} characters).` },
        model: { type: 'string', description: 'Optional model, e.g. gemini-3.7-flash-medium.' },
        effort: { type: 'string', enum: ['low', 'medium', 'high'], description: 'Optional reasoning effort.' },
      },
      required: ['prompt'],
    },
  },
  async handler(args) {
    const prompt = typeof args.prompt === 'string' ? args.prompt.trim() : '';
    if (!prompt) return err('prompt is required');
    if (prompt.length > MAX_PROMPT_CHARS) return err(`prompt exceeds ${MAX_PROMPT_CHARS} characters`);
    const model = typeof args.model === 'string' ? args.model.trim() : undefined;
    if (model && (!MODEL_RE.test(model) || !AGY_MODELS.has(model)))
      return err('model is not in the approved Gemini catalog');
    const effort = typeof args.effort === 'string' ? args.effort.toLowerCase() : undefined;
    if (effort && !EFFORTS.has(effort)) return err('effort must be low, medium, or high');
    try {
      const raw = await runNcl({ request_id: generateId(), prompt, model, effort });
      const frame = JSON.parse(raw) as { ok?: boolean; data?: unknown; error?: { message?: string } };
      if (!frame.ok) return err(frame.error?.message || 'Antigravity request failed');
      return ok(JSON.stringify(frame.data));
    } catch (error) {
      return err(error instanceof Error ? error.message : String(error));
    }
  },
};

registerTools([runAgy]);
