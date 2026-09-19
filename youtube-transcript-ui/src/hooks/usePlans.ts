/**
 * TanStack Query hooks for the plan/apply engine.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { plansApi } from '@/api/plans';
import type { CreatePlanRequest } from '@/api/types';

// Query key factory for type-safe cache invalidation
export const planKeys = {
  all: ['plans'] as const,
  detail: (planId: string) => [...planKeys.all, 'detail', planId] as const,
};

export const quotaKeys = {
  all: ['quota'] as const,
};

/**
 * Fetch a plan and its ordered ops, with quota unit rollups.
 */
export function usePlan(planId: string) {
  return useQuery({
    queryKey: planKeys.detail(planId),
    queryFn: () => plansApi.getPlan(planId),
    enabled: !!planId,
  });
}

/**
 * Create a plan for a given generation strategy (e.g. a new playlist).
 */
export function useCreatePlan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: CreatePlanRequest) => plansApi.createPlan(request),
    onSuccess: (data) => {
      queryClient.setQueryData(planKeys.detail(data.id), data);
    },
  });
}

/**
 * Apply a plan, up to an optional per-invocation budget.
 */
export function useApplyPlan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ planId, budgetUnits }: { planId: string; budgetUnits?: number | null }) =>
      plansApi.applyPlan(planId, budgetUnits),
    onSuccess: (data) => {
      queryClient.setQueryData(planKeys.detail(data.id), data);
      queryClient.invalidateQueries({ queryKey: quotaKeys.all });
    },
  });
}

/**
 * Fetch the shared, app-wide YouTube Data API daily quota status.
 */
export function useQuota() {
  return useQuery({
    queryKey: quotaKeys.all,
    queryFn: plansApi.getQuota,
  });
}
