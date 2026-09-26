/**
 * Document API endpoints.
 */

import { apiClient, ApiError, tokenStorage } from './client';
import type {
  Document,
  SessionDocumentsResponse,
  DocumentListResponse,
  DocumentListParams,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001';

export const documentsApi = {
  /**
   * List documents for a session.
   */
  listForSession: (sessionId: string) =>
    apiClient<SessionDocumentsResponse>(`/api/sessions/${sessionId}/documents`),

  /**
   * Upload a document to a session.
   * Uses FormData for file upload instead of JSON.
   */
  upload: async (sessionId: string, file: File): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = tokenStorage.getAccessToken();
    const headers: Record<string, string> = {};

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    // Note: Don't set Content-Type - browser sets it with boundary for FormData

    const response = await fetch(
      `${API_BASE_URL}/api/sessions/${sessionId}/documents`,
      {
        method: 'POST',
        headers,
        body: formData,
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new ApiError(response.status, error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  },

  /**
   * Delete a document from a session.
   */
  delete: (sessionId: string, documentId: string) =>
    apiClient<{ message: string }>(
      `/api/sessions/${sessionId}/documents/${documentId}`,
      { method: 'DELETE' }
    ),

  /**
   * List all user documents with optional filtering and pagination.
   */
  list: (params?: DocumentListParams) => {
    const searchParams = new URLSearchParams();
    if (params?.skip !== undefined) searchParams.set('skip', String(params.skip));
    if (params?.limit !== undefined) searchParams.set('limit', String(params.limit));
    if (params?.search) searchParams.set('search', params.search);

    const queryString = searchParams.toString();
    const endpoint = `/api/documents${queryString ? `?${queryString}` : ''}`;
    return apiClient<DocumentListResponse>(endpoint);
  },

  /**
   * Get a single document by ID.
   */
  get: (documentId: string) =>
    apiClient<Document>(`/api/documents/${documentId}`),
};
