/**
 * Cross-Chat API endpoints.
 */

import { apiClient } from './client';
import type {
  CrossChatSession,
  CrossChatSessionDetail,
  CrossChatSessionListResponse,
  CrossChatQueryResponse,
} from './types';

export const crossChatApi = {
  /**
   * Create a new cross-chat session referencing multiple transcript sessions.
   */
  create: (sessionIds: string[], modelProvider?: string) =>
    apiClient<CrossChatSession>('/api/cross-chat/sessions', {
      method: 'POST',
      body: JSON.stringify({
        session_ids: sessionIds,
        model_provider: modelProvider,
      }),
    }),

  /**
   * List all cross-chat sessions.
   */
  list: () =>
    apiClient<CrossChatSessionListResponse>('/api/cross-chat/sessions'),

  /**
   * Get a cross-chat session with full conversation history.
   */
  get: (id: string) =>
    apiClient<CrossChatSessionDetail>(`/api/cross-chat/sessions/${id}`),

  /**
   * Send a query within a cross-chat session.
   */
  query: (id: string, question: string) =>
    apiClient<CrossChatQueryResponse>(`/api/cross-chat/sessions/${id}/query`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),

  /**
   * Delete a cross-chat session.
   */
  delete: (id: string) =>
    apiClient<{ message: string }>(`/api/cross-chat/sessions/${id}`, {
      method: 'DELETE',
    }),
};
