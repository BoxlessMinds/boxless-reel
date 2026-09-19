/**
 * TanStack Query hooks for cross-chat operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { crossChatApi } from '@/api/crossChat';

// Query key factory for type-safe cache invalidation
export const crossChatKeys = {
  all: ['cross-chat'] as const,
  lists: () => [...crossChatKeys.all, 'list'] as const,
  list: () => [...crossChatKeys.lists()] as const,
  details: () => [...crossChatKeys.all, 'detail'] as const,
  detail: (id: string) => [...crossChatKeys.details(), id] as const,
};

/**
 * Fetch all cross-chat sessions.
 */
export function useCrossChatSessions() {
  return useQuery({
    queryKey: crossChatKeys.list(),
    queryFn: () => crossChatApi.list(),
  });
}

/**
 * Fetch a single cross-chat session with messages.
 */
export function useCrossChatSession(id: string) {
  return useQuery({
    queryKey: crossChatKeys.detail(id),
    queryFn: () => crossChatApi.get(id),
    enabled: !!id,
  });
}

/**
 * Create a new cross-chat session.
 */
export function useCreateCrossChatSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      sessionIds,
      modelProvider,
    }: {
      sessionIds: string[];
      modelProvider?: string;
    }) => crossChatApi.create(sessionIds, modelProvider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: crossChatKeys.lists() });
    },
  });
}

/**
 * Send a query within a cross-chat session.
 */
export function useQueryCrossChatSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, question }: { id: string; question: string }) =>
      crossChatApi.query(id, question),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: crossChatKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: crossChatKeys.lists() });
    },
  });
}

/**
 * Delete a cross-chat session.
 */
export function useDeleteCrossChatSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: crossChatApi.delete,
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: crossChatKeys.lists() });
      queryClient.removeQueries({ queryKey: crossChatKeys.detail(deletedId) });
    },
  });
}
