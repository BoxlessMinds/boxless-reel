/**
 * Invitations hooks using TanStack Query.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { invitationsApi } from '@/api/invitations';
import type { InvitationCreateRequest } from '@/api/types';

// Query keys
export const invitationKeys = {
  all: ['invitations'] as const,
  lists: () => [...invitationKeys.all, 'list'] as const,
  validation: (token: string) => [...invitationKeys.all, 'validate', token] as const,
};

/**
 * Hook for listing invitations sent by the current user.
 */
export function useInvitations() {
  return useQuery({
    queryKey: invitationKeys.lists(),
    queryFn: invitationsApi.list,
  });
}

/**
 * Hook for creating a new invitation.
 */
export function useCreateInvitation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: invitationsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: invitationKeys.lists() });
    },
  });
}

/**
 * Hook for revoking an invitation.
 */
export function useRevokeInvitation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: invitationsApi.revoke,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: invitationKeys.lists() });
    },
  });
}

/**
 * Hook for clearing (permanently deleting) an invitation.
 */
export function useClearInvitation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: invitationsApi.clear,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: invitationKeys.lists() });
    },
  });
}

/**
 * Hook for validating an invitation token.
 */
export function useValidateInvitationToken(token: string | null) {
  return useQuery({
    queryKey: invitationKeys.validation(token ?? ''),
    queryFn: () => invitationsApi.validateToken(token!),
    enabled: !!token,
    retry: false,
  });
}
