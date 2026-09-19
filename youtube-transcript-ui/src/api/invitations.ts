/**
 * Invitations API endpoints.
 */

import { apiClient, publicApiClient } from './client';
import type {
  Invitation,
  InvitationCreateRequest,
  InvitationListResponse,
  InvitationValidateResponse,
} from './types';

export const invitationsApi = {
  /**
   * Create a new invitation.
   */
  create: (data: InvitationCreateRequest): Promise<Invitation> => {
    return apiClient<Invitation>('/api/invitations', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * List invitations sent by the current user.
   */
  list: (): Promise<InvitationListResponse> => {
    return apiClient<InvitationListResponse>('/api/invitations');
  },

  /**
   * Revoke a pending invitation.
   */
  revoke: (invitationId: string): Promise<{ message: string }> => {
    return apiClient<{ message: string }>(`/api/invitations/${invitationId}`, {
      method: 'DELETE',
    });
  },

  /**
   * Clear (permanently delete) an invitation from history.
   */
  clear: (invitationId: string): Promise<{ message: string }> => {
    return apiClient<{ message: string }>(`/api/invitations/${invitationId}/clear`, {
      method: 'DELETE',
    });
  },

  /**
   * Validate an invitation token (public endpoint).
   */
  validateToken: (token: string): Promise<InvitationValidateResponse> => {
    return publicApiClient<InvitationValidateResponse>(
      '/api/invitations/validate',
      {
        method: 'POST',
        body: JSON.stringify({ token }),
      }
    );
  },
};
