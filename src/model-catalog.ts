import fs from 'node:fs';
import path from 'node:path';

import { DATA_DIR } from './config.js';

/** Approved AGY model IDs; the provider still enforces account availability. */
export const AGY_MODELS = [
  'gemini-4-argon',
  'gemini-4-argon-high',
  'gemini-4-argon-medium',
  'gemini-4-argon-low',
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
] as const;

/** Fallback catalog for Codex 0.160; Telegram prefers the account's refreshed catalog. */
export const CODEX_MODELS = [
  'gpt-6.1-sol',
  'gpt-6-astra',
  'gpt-6-sol',
  'gpt-6-luna',
  'gpt-5.6-sol',
  'gpt-5.6-terra',
  'gpt-5.6-luna',
  'gpt-5.5',
] as const;

/** Codex refreshes this catalog when its authenticated provider starts. */
export function getCodexModels(agentGroupId: string): readonly string[] {
  if (!/^[a-zA-Z0-9_-]+$/.test(agentGroupId)) return CODEX_MODELS;
  try {
    const cache = JSON.parse(
      fs.readFileSync(path.join(DATA_DIR, 'v2-sessions', agentGroupId, '.codex-shared', 'models_cache.json'), 'utf8'),
    );
    if (!Array.isArray(cache?.models)) return CODEX_MODELS;
    return cache.models
      .filter(
        (model: { visibility?: string; slug?: string } | null) =>
          model?.visibility === 'list' &&
          typeof model.slug === 'string' &&
          /^[a-z0-9][a-z0-9._-]{0,79}$/i.test(model.slug),
      )
      .map((model: { slug: string }) => model.slug);
  } catch (error) {
    if (error instanceof SyntaxError || (error as NodeJS.ErrnoException).code === 'ENOENT') return CODEX_MODELS;
    throw error;
  }
}

export function formatModelCatalog(
  current: string | null | undefined,
  codexModels: readonly string[] = CODEX_MODELS,
): string {
  return [
    `Main NanoClaw model: ${current ?? 'default'}`,
    '',
    'Antigravity (/run_agy) models:',
    ...AGY_MODELS.map((model) => `• ${model}`),
    '',
    'Codex (/model) models:',
    ...codexModels.map((model) => `• ${model}`),
    '',
    'Use /model <name> to change NanoClaw’s main Codex provider. The Antigravity worker is selected per run by the tool.',
  ].join('\n');
}
