/**
 * Admin hooks using TanStack Query.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi, type UserListFilters } from '@/api/admin';
import type { AdminUserUpdateRequest } from '@/api/types';

// Query keys
export const adminKeys = {
  all: ['admin'] as const,
  users: () => [...adminKeys.all, 'users'] as const,
  usersList: (filters: UserListFilters) => [...adminKeys.users(), filters] as const,
  invitations: () => [...adminKeys.all, 'invitations'] as const,
  registrationMode: () => [...adminKeys.all, 'registrationMode'] as const,
};

/**
 * Hook for listing all users (admin only).
 */
export function useAdminUsers(filters: UserListFilters = {}) {
  return useQuery({
    queryKey: adminKeys.usersList(filters),
    queryFn: () => adminApi.listUsers(filters),
  });
}

/**
 * Hook for updating a user (admin only).
 */
export function useAdminUpdateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: AdminUserUpdateRequest }) =>
      adminApi.updateUser(userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() });
    },
  });
}

/**
 * Hook for deleting a user (admin only).
 */
export function useAdminDeleteUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) => adminApi.deleteUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() });
    },
  });
}

/**
 * Hook for listing all invitations (admin only).
 */
export function useAdminInvitations() {
  return useQuery({
    queryKey: adminKeys.invitations(),
    queryFn: adminApi.listAllInvitations,
  });
}

/**
 * Hook for bulk creating invitations (admin only).
 */
export function useAdminBulkInvitations() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: adminApi.bulkCreateInvitations,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.invitations() });
    },
  });
}

/**
 * Hook for getting the current registration mode (admin only).
 */
export function useAdminRegistrationMode() {
  return useQuery({
    queryKey: adminKeys.registrationMode(),
    queryFn: adminApi.getRegistrationMode,
  });
}

/**
 * Hook for updating the registration mode (admin only).
 */
export function useAdminUpdateRegistrationMode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (requireInvitation: boolean) =>
      adminApi.updateRegistrationMode(requireInvitation),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.registrationMode() });
    },
  });
}
