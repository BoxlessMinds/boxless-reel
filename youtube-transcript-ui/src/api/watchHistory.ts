/**
 * Watch history import API endpoints.
 */

import { apiClient, ApiError, tokenStorage } from './client';
import type { WatchHistoryImport, WatchHistoryImportListResponse, WatchHistoryListParams } from './types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export const watchHistoryApi = {
  /**
   * Upload a Google Takeout watch-history.json for parsing and storage.
   * Uses FormData for file upload instead of JSON.
   */
  upload: async (file: File): Promise<WatchHistoryImport> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = tokenStorage.getAccessToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    // Note: Don't set Content-Type - browser sets it with boundary for FormData

    const response = await fetch(`${API_BASE_URL}/api/watch-history/import`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Import failed' }));
      throw new ApiError(response.status, error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  },

  /**
   * List past watch-history imports for the current user.
   */
  list: (params?: WatchHistoryListParams) => {
    const searchParams = new URLSearchParams();
    if (params?.skip !== undefined) searchParams.set('skip', String(params.skip));
    if (params?.limit !== undefined) searchParams.set('limit', String(params.limit));

    const queryString = searchParams.toString();
    const endpoint = `/api/watch-history${queryString ? `?${queryString}` : ''}`;
    return apiClient<WatchHistoryImportListResponse>(endpoint);
  },
};
