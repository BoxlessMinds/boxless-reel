/**
 * Admin API endpoints.
 */

import { apiClient } from './client';
import type {
  User,
  AdminUserUpdateRequest,
  UserListResponse,
  InvitationListResponse,
  BulkInvitationRequest,
  BulkInvitationResponse,
  RegistrationMode,
} from './types';

export interface UserListFilters {
  search?: string;
  role?: 'admin' | 'user';
  is_active?: boolean;
  page?: number;
  page_size?: number;
}

export const adminApi = {
  /**
   * List all users (admin only).
   */
  listUsers: (filters: UserListFilters = {}): Promise<UserListResponse> => {
    const params = new URLSearchParams();
    if (filters.search) params.append('search', filters.search);
    if (filters.role) params.append('role', filters.role);
    if (filters.is_active !== undefined) params.append('is_active', String(filters.is_active));
    if (filters.page) params.append('page', String(filters.page));
    if (filters.page_size) params.append('page_size', String(filters.page_size));

    const queryString = params.toString();
    return apiClient<UserListResponse>(
      `/api/admin/users${queryString ? `?${queryString}` : ''}`
    );
  },

  /**
   * Update a user's status or role (admin only).
   */
  updateUser: (userId: string, data: AdminUserUpdateRequest): Promise<User> => {
    return apiClient<User>(`/api/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /**
   * Delete a user (admin only).
   */
  deleteUser: (userId: string): Promise<{ message: string }> => {
    return apiClient<{ message: string }>(`/api/admin/users/${userId}`, {
      method: 'DELETE',
    });
  },

  /**
   * List all invitations (admin only).
   */
  listAllInvitations: (): Promise<InvitationListResponse> => {
    return apiClient<InvitationListResponse>('/api/admin/invitations');
  },

  /**
   * Create multiple invitations at once (admin only).
   */
  bulkCreateInvitations: (data: BulkInvitationRequest): Promise<BulkInvitationResponse> => {
    return apiClient<BulkInvitationResponse>('/api/admin/invitations/bulk', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Get current registration mode (admin only).
   */
  getRegistrationMode: (): Promise<RegistrationMode> => {
    return apiClient<RegistrationMode>('/api/admin/settings/registration-mode');
  },

  /**
   * Update registration mode (admin only).
   */
  updateRegistrationMode: (requireInvitation: boolean): Promise<RegistrationMode> => {
    return apiClient<RegistrationMode>('/api/admin/settings/registration-mode', {
      method: 'PUT',
      body: JSON.stringify({ require_invitation: requireInvitation }),
    });
  },
};
