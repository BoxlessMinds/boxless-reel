/**
 * TanStack Query hooks for document operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { documentsApi } from '@/api/documents';
import type { DocumentListParams } from '@/api/types';

// Query key factory for type-safe cache invalidation
export const documentKeys = {
  all: ['documents'] as const,
  lists: () => [...documentKeys.all, 'list'] as const,
  list: (params?: DocumentListParams) => [...documentKeys.lists(), params] as const,
  details: () => [...documentKeys.all, 'detail'] as const,
  detail: (id: string) => [...documentKeys.details(), id] as const,
  sessions: () => [...documentKeys.all, 'session'] as const,
  session: (sessionId: string) => [...documentKeys.sessions(), sessionId] as const,
};

/**
 * Fetch documents for a specific session.
 */
export function useSessionDocuments(sessionId: string | null) {
  return useQuery({
    queryKey: documentKeys.session(sessionId || ''),
    queryFn: () => documentsApi.listForSession(sessionId!),
    enabled: !!sessionId,
  });
}

/**
 * Upload a document to a session.
 */
export function useUploadDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sessionId, file }: { sessionId: string; file: File }) =>
      documentsApi.upload(sessionId, file),
    onSuccess: (_, { sessionId }) => {
      // Invalidate session documents to refetch
      queryClient.invalidateQueries({ queryKey: documentKeys.session(sessionId) });
      // Also invalidate the global documents list
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}

/**
 * Delete a document from a session.
 */
export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      sessionId,
      documentId,
    }: {
      sessionId: string;
      documentId: string;
    }) => documentsApi.delete(sessionId, documentId),
    onSuccess: (_, { sessionId, documentId }) => {
      // Invalidate session documents
      queryClient.invalidateQueries({ queryKey: documentKeys.session(sessionId) });
      // Remove from global documents list cache
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      // Remove specific document detail from cache
      queryClient.removeQueries({ queryKey: documentKeys.detail(documentId) });
    },
  });
}

/**
 * List all user documents with optional filtering and pagination.
 */
export function useDocuments(params?: DocumentListParams) {
  return useQuery({
    queryKey: documentKeys.list(params),
    queryFn: () => documentsApi.list(params),
  });
}

/**
 * Fetch a single document by ID.
 */
export function useDocument(documentId: string) {
  return useQuery({
    queryKey: documentKeys.detail(documentId),
    queryFn: () => documentsApi.get(documentId),
    enabled: !!documentId,
  });
}
