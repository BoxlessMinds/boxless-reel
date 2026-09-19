/**
 * Session API endpoints.
 */

import { apiClient } from './client';
import type {
  Session,
  SessionDetail,
  SessionListResponse,
  QueryResponse,
} from './types';

export const sessionsApi = {
  /**
   * List all sessions.
   */
  list: (transcriptId?: string) => {
    const params = transcriptId ? `?transcript_id=${transcriptId}` : '';
    return apiClient<SessionListResponse>(`/api/sessions${params}`);
  },

  /**
   * Get a session with full conversation history.
   */
  get: (sessionId: string) =>
    apiClient<SessionDetail>(`/api/sessions/${sessionId}`),

  /**
   * Delete a session.
   */
  delete: (sessionId: string) =>
    apiClient<{ message: string }>(`/api/sessions/${sessionId}`, {
      method: 'DELETE',
    }),

  /**
   * Create a new session for a transcript.
   */
  create: (transcriptId: string, modelProvider?: string) =>
    apiClient<Session>(`/api/transcripts/${transcriptId}/sessions`, {
      method: 'POST',
      body: JSON.stringify({ model_provider: modelProvider }),
    }),

  /**
   * Query within an existing session.
   */
  query: (sessionId: string, question: string) =>
    apiClient<QueryResponse>(`/api/sessions/${sessionId}/query`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),

  /**
   * One-shot query without creating a session.
   */
  queryOneshot: (transcriptId: string, question: string) =>
    apiClient<QueryResponse>(`/api/transcripts/${transcriptId}/query`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
};
