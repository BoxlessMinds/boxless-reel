/**
 * TanStack Query hooks for Google/YouTube account connection.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { youtubeAuthApi } from '@/api/youtubeAuth';

// Query key factory for type-safe cache invalidation
export const youtubeAuthKeys = {
  all: ['youtube-auth'] as const,
  status: () => [...youtubeAuthKeys.all, 'status'] as const,
};

/**
 * Fetch the current Google/YouTube connection status.
 */
export function useYoutubeAuthStatus(enabled: boolean = true) {
  return useQuery({
    queryKey: youtubeAuthKeys.status(),
    queryFn: () => youtubeAuthApi.getStatus(),
    staleTime: 30000,
    enabled,
  });
}

/**
 * Start the Google OAuth consent flow.
 */
export function useConnectYoutube() {
  return useMutation({
    mutationFn: () => youtubeAuthApi.connect(),
  });
}

/**
 * Disconnect the connected Google account.
 */
export function useDisconnectYoutube() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => youtubeAuthApi.disconnect(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: youtubeAuthKeys.all });
    },
  });
}
