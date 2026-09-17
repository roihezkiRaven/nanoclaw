/** Models exposed by the authenticated Antigravity CLI on the assistant VPS. */
export const AGY_MODELS = [
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

// Codex models are selected by NanoClaw's primary provider (/model), not by
// the Antigravity worker. Keep this list conservative and limited to names
// exercised by the installed Codex provider; availability remains account-
// dependent and the provider will reject unavailable names.
export const CODEX_MODELS = ['gpt-5', 'gpt-5.5'] as const;

export function formatModelCatalog(current: string | null | undefined): string {
  return [
    `Main NanoClaw model: ${current ?? 'default'}`,
    '',
    'Antigravity (/run_agy) models:',
    ...AGY_MODELS.map((model) => `• ${model}`),
    '',
    'Codex (/model) models:',
    ...CODEX_MODELS.map((model) => `• ${model}`),
    '',
    'Use /model <name> to change NanoClaw’s main Codex provider. The Antigravity worker is selected per run by the tool.',
  ].join('\n');
}
