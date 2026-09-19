/**
 * Plan/apply engine API endpoints.
 */

import { apiClient } from './client';
import type { Plan, ApplyPlanRequest, CreatePlanRequest, QuotaResponse } from './types';

export const plansApi = {
  /**
   * Create a plan for a given generation strategy (e.g. `kind: "create"` for
   * a new playlist), producing ops for review via getPlan before applying.
   */
  createPlan: (request: CreatePlanRequest): Promise<Plan> => {
    return apiClient<Plan>('/api/plans', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  /**
   * Get a plan and its ordered ops, with quota unit rollups.
   */
  getPlan: (planId: string): Promise<Plan> => {
    return apiClient<Plan>(`/api/plans/${planId}`);
  },

  /**
   * Apply a plan: execute its pending ops in sequence order, up to budget.
   */
  applyPlan: (planId: string, budgetUnits?: number | null): Promise<Plan> => {
    const body: ApplyPlanRequest = { budget_units: budgetUnits ?? null };
    return apiClient<Plan>(`/api/plans/${planId}/apply`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  /**
   * Get the shared, app-wide YouTube Data API daily quota status.
   */
  getQuota: (): Promise<QuotaResponse> => {
    return apiClient<QuotaResponse>('/api/playlists/quota');
  },
};
