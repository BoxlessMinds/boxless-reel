/**
 * Settings API endpoints.
 */

import { apiClient } from './client';
import type {
  LLMSettings,
  LLMSettingsUpdate,
  ValidateKeyResponse,
} from './types';

export const settingsApi = {
  /**
   * Get current LLM settings.
   */
  get: () => apiClient<LLMSettings>('/api/settings'),

  /**
   * Update LLM settings.
   */
  update: (settings: LLMSettingsUpdate) =>
    apiClient<LLMSettings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),

  /**
   * Validate an API key before saving.
   */
  validateKey: (provider: 'anthropic' | 'openai', apiKey: string) =>
    apiClient<ValidateKeyResponse>('/api/settings/validate-key', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key: apiKey }),
    }),
};
