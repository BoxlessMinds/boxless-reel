/**
 * Transcript API endpoints.
 */

import { apiClient } from './client';
import type {
  Transcript,
  TranscriptListResponse,
  TranscriptExtractRequest,
} from './types';

export interface TranscriptFilters {
  search?: string;
  language?: string;
  page?: number;
  page_size?: number;
}

export const transcriptsApi = {
  /**
   * Extract a transcript from a YouTube URL.
   */
  extract: (data: TranscriptExtractRequest) =>
    apiClient<Transcript>('/api/transcripts/extract', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /**
   * List transcripts with optional filtering and pagination.
   */
  list: (filters: TranscriptFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.search) params.set('search', filters.search);
    if (filters.language) params.set('language', filters.language);
    if (filters.page) params.set('page', filters.page.toString());
    if (filters.page_size) params.set('page_size', filters.page_size.toString());

    const query = params.toString();
    return apiClient<TranscriptListResponse>(
      `/api/transcripts${query ? `?${query}` : ''}`
    );
  },

  /**
   * Get a single transcript by ID.
   */
  get: (id: string) => apiClient<Transcript>(`/api/transcripts/${id}`),

  /**
   * Delete a transcript by ID.
   */
  delete: (id: string) =>
    apiClient<{ message: string }>(`/api/transcripts/${id}`, {
      method: 'DELETE',
    }),
};
