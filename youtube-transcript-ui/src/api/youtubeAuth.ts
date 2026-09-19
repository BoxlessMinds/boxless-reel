/**
 * Google/YouTube account connection API endpoints.
 */

import { apiClient } from './client';

export interface YoutubeAuthStatus {
  connected: boolean;
  google_account_email: string | null;
  token_expires_at: string | null;
}

export interface YoutubeAuthConnectResponse {
  authorization_url: string;
}

export interface YoutubeAuthDisconnectResponse {
  message: string;
}

export const youtubeAuthApi = {
  /**
   * Get the current Google/YouTube connection status.
   */
  getStatus: () => apiClient<YoutubeAuthStatus>('/api/youtube-auth/status'),

  /**
   * Start the Google OAuth consent flow. Returns the URL to redirect the browser to.
   */
  connect: () => apiClient<YoutubeAuthConnectResponse>('/api/youtube-auth/connect'),

  /**
   * Disconnect the connected Google account.
   */
  disconnect: () =>
    apiClient<YoutubeAuthDisconnectResponse>('/api/youtube-auth/disconnect', {
      method: 'DELETE',
    }),
};
