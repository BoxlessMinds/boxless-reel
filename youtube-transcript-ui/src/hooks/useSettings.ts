/**
 * TanStack Query hooks for settings operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsApi } from '@/api/settings';
import type { LLMSettingsUpdate } from '@/api/types';

// Query key factory for type-safe cache invalidation
export const settingsKeys = {
  all: ['settings'] as const,
  detail: () => [...settingsKeys.all, 'detail'] as const,
};

/**
 * Fetch current LLM settings.
 * Only fetches when enabled (user is authenticated).
 */
export function useSettings(enabled: boolean = true) {
  return useQuery({
    queryKey: settingsKeys.detail(),
    queryFn: () => settingsApi.get(),
    staleTime: 30000, // Consider settings fresh for 30 seconds
    enabled,
  });
}

/**
 * Update LLM settings.
 */
export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (settings: LLMSettingsUpdate) => settingsApi.update(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: settingsKeys.all });
    },
  });
}

/**
 * Validate an API key before saving.
 */
export function useValidateApiKey() {
  return useMutation({
    mutationFn: ({
      provider,
      apiKey,
    }: {
      provider: 'anthropic' | 'openai';
      apiKey: string;
    }) => settingsApi.validateKey(provider, apiKey),
  });
}
