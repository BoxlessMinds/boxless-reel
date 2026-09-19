/**
 * Auth hooks using TanStack Query for data fetching.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi } from '@/api/auth';
import type { LoginRequest, RegisterRequest, UserUpdateRequest, User } from '@/api/types';

// Query keys
export const authKeys = {
  all: ['auth'] as const,
  user: () => [...authKeys.all, 'user'] as const,
};

/**
 * Hook for login mutation.
 */
export function useLogin() {
  return useMutation({
    mutationFn: authApi.login,
  });
}

/**
 * Hook for register mutation.
 */
export function useRegister() {
  return useMutation({
    mutationFn: authApi.register,
  });
}

/**
 * Hook for logout mutation.
 */
export function useLogout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: authApi.logout,
    onSuccess: () => {
      // Clear all queries on logout
      queryClient.clear();
    },
  });
}

/**
 * Hook for fetching current user.
 */
export function useUser(enabled: boolean = true) {
  return useQuery({
    queryKey: authKeys.user(),
    queryFn: authApi.getMe,
    enabled,
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook for updating user profile.
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: authApi.updateProfile,
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(authKeys.user(), updatedUser);
    },
  });
}
