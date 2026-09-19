/**
 * TanStack Query hooks for transcript operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { transcriptsApi, type TranscriptFilters } from '@/api/transcripts';

// Query key factory for type-safe cache invalidation
export const transcriptKeys = {
  all: ['transcripts'] as const,
  lists: () => [...transcriptKeys.all, 'list'] as const,
  list: (filters: TranscriptFilters) => [...transcriptKeys.lists(), filters] as const,
  details: () => [...transcriptKeys.all, 'detail'] as const,
  detail: (id: string) => [...transcriptKeys.details(), id] as const,
};

/**
 * Fetch a list of transcripts with optional filtering and pagination.
 */
export function useTranscripts(filters: TranscriptFilters = {}) {
  return useQuery({
    queryKey: transcriptKeys.list(filters),
    queryFn: () => transcriptsApi.list(filters),
  });
}

/**
 * Fetch a single transcript by ID.
 */
export function useTranscript(id: string) {
  return useQuery({
    queryKey: transcriptKeys.detail(id),
    queryFn: () => transcriptsApi.get(id),
    enabled: !!id,
  });
}

/**
 * Extract a new transcript from a YouTube URL.
 */
export function useExtractTranscript() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: transcriptsApi.extract,
    onSuccess: () => {
      // Invalidate all transcript lists to refetch
      queryClient.invalidateQueries({ queryKey: transcriptKeys.lists() });
    },
  });
}

/**
 * Delete a transcript by ID.
 */
export function useDeleteTranscript() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: transcriptsApi.delete,
    onSuccess: (_, deletedId) => {
      // Invalidate lists and remove the deleted transcript from cache
      queryClient.invalidateQueries({ queryKey: transcriptKeys.lists() });
      queryClient.removeQueries({ queryKey: transcriptKeys.detail(deletedId) });
    },
  });
}
