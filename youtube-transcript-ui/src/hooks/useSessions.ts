/**
 * TanStack Query hooks for session operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { sessionsApi } from '@/api/sessions';

// Query key factory for type-safe cache invalidation
export const sessionKeys = {
  all: ['sessions'] as const,
  lists: () => [...sessionKeys.all, 'list'] as const,
  list: (transcriptId?: string) => [...sessionKeys.lists(), transcriptId] as const,
  details: () => [...sessionKeys.all, 'detail'] as const,
  detail: (id: string) => [...sessionKeys.details(), id] as const,
};

/**
 * Fetch all sessions, optionally filtered by transcript ID.
 */
export function useSessions(transcriptId?: string) {
  return useQuery({
    queryKey: sessionKeys.list(transcriptId),
    queryFn: () => sessionsApi.list(transcriptId),
  });
}

/**
 * Fetch a session with full conversation history.
 */
export function useSession(sessionId: string) {
  return useQuery({
    queryKey: sessionKeys.detail(sessionId),
    queryFn: () => sessionsApi.get(sessionId),
    enabled: !!sessionId,
  });
}

/**
 * Create a new session for a transcript.
 */
export function useCreateSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      transcriptId,
      modelProvider,
    }: {
      transcriptId: string;
      modelProvider?: string;
    }) => sessionsApi.create(transcriptId, modelProvider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sessionKeys.lists() });
    },
  });
}

/**
 * Delete a session.
 */
export function useDeleteSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: sessionsApi.delete,
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: sessionKeys.lists() });
      queryClient.removeQueries({ queryKey: sessionKeys.detail(deletedId) });
    },
  });
}

/**
 * Query within an existing session.
 */
export function useQuerySession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sessionId, question }: { sessionId: string; question: string }) =>
      sessionsApi.query(sessionId, question),
    onSuccess: (_, { sessionId }) => {
      // Refetch session to get updated history
      queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });
      queryClient.invalidateQueries({ queryKey: sessionKeys.lists() });
    },
  });
}

/**
 * One-shot query without session persistence.
 */
export function useQueryOneshot() {
  return useMutation({
    mutationFn: ({
      transcriptId,
      question,
    }: {
      transcriptId: string;
      question: string;
    }) => sessionsApi.queryOneshot(transcriptId, question),
  });
}
