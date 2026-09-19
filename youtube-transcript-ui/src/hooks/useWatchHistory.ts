/**
 * TanStack Query hooks for watch history imports.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { watchHistoryApi } from '@/api/watchHistory';
import type { WatchHistoryListParams } from '@/api/types';

// Query key factory for type-safe cache invalidation
export const watchHistoryKeys = {
  all: ['watchHistory'] as const,
  lists: () => [...watchHistoryKeys.all, 'list'] as const,
  list: (params?: WatchHistoryListParams) => [...watchHistoryKeys.lists(), params] as const,
};

/**
 * List past watch-history imports for the current user.
 */
export function useWatchHistoryImports(params?: WatchHistoryListParams) {
  return useQuery({
    queryKey: watchHistoryKeys.list(params),
    queryFn: () => watchHistoryApi.list(params),
  });
}

/**
 * Upload a Google Takeout watch-history.json for parsing and storage.
 */
export function useUploadWatchHistory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => watchHistoryApi.upload(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchHistoryKeys.lists() });
    },
  });
}
