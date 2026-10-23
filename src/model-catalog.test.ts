import fs from 'node:fs';
import { afterEach, expect, it, vi } from 'vitest';

import { CODEX_MODELS, formatModelCatalog, getCodexModels } from './model-catalog.js';

afterEach(() => vi.restoreAllMocks());

it('lists the GPT-6 family in the catalog used by Telegram /models', () => {
  const catalog = formatModelCatalog('gpt-6.1-sol');
  for (const model of ['gpt-6-sol', 'gpt-6-luna', 'gpt-6-astra', 'gpt-6.1-sol']) {
    expect(catalog).toContain(`• ${model}`);
  }
  expect(catalog).toContain('Main NanoClaw model: gpt-6.1-sol');
});

it('uses the account catalog and excludes hidden or invalid model entries', () => {
  vi.spyOn(fs, 'readFileSync').mockReturnValue(
    JSON.stringify({
      models: [
        { slug: 'gpt-6.1-sol', visibility: 'list' },
        { slug: 'future-model', visibility: 'list' },
        { slug: 'internal-model', visibility: 'hide' },
        { slug: '<invalid>', visibility: 'list' },
        null,
      ],
    }),
  );
  const models = getCodexModels('ag-test');
  expect(models).toEqual(['gpt-6.1-sol', 'future-model']);
  expect(formatModelCatalog(null, models)).toContain('• future-model');
  expect(formatModelCatalog(null, models)).not.toContain('internal-model');
});

it('falls back when the account catalog is missing or corrupt', () => {
  vi.spyOn(fs, 'readFileSync').mockReturnValue('{broken');
  expect(getCodexModels('ag-test')).toEqual(CODEX_MODELS);
});
