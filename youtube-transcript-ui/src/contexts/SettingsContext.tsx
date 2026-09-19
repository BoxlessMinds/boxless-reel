/**
 * Settings context for global access to LLM configuration.
 */

import { createContext, useContext, useEffect, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSettings, useUpdateSettings, settingsKeys } from '@/hooks/useSettings';
import { useAuth } from '@/contexts/AuthContext';
import type { LLMSettings, LLMSettingsUpdate } from '@/api/types';

interface SettingsContextValue {
  settings: LLMSettings | null;
  isLoading: boolean;
  error: Error | null;
  updateSettings: (settings: LLMSettingsUpdate) => Promise<LLMSettings>;
  refetch: () => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

interface SettingsProviderProps {
  children: ReactNode;
}

export function SettingsProvider({ children }: SettingsProviderProps) {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useSettings(isAuthenticated);
  const updateMutation = useUpdateSettings();

  // Clear settings cache when user logs out
  useEffect(() => {
    if (!isAuthenticated) {
      queryClient.removeQueries({ queryKey: settingsKeys.all });
    }
  }, [isAuthenticated, queryClient]);

  const value: SettingsContextValue = {
    settings: data ?? null,
    isLoading: isAuthenticated ? isLoading : false,
    error: error as Error | null,
    updateSettings: async (settings: LLMSettingsUpdate) => {
      return updateMutation.mutateAsync(settings);
    },
    refetch,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettingsContext() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettingsContext must be used within SettingsProvider');
  }
  return context;
}
