/**
 * Playlist API endpoints.
 */

import { apiClient } from './client';
import type {
  PlaylistListResponse,
  PlaylistItemListResponse,
  PlaylistSyncResponse,
} from './types';

export interface PlaylistFilters {
  page?: number;
  page_size?: number;
}

export const playlistsApi = {
  /**
   * Trigger a full re-sync of the current user's owned playlists.
   */
  sync: () =>
    apiClient<PlaylistSyncResponse>('/api/playlists/sync', {
      method: 'POST',
    }),

  /**
   * List cached playlists with pagination.
   */
  list: (filters: PlaylistFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.page) params.set('page', filters.page.toString());
    if (filters.page_size) params.set('page_size', filters.page_size.toString());

    const query = params.toString();
    return apiClient<PlaylistListResponse>(
      `/api/playlists${query ? `?${query}` : ''}`
    );
  },

  /**
   * List items for a single playlist, paginated.
   */
  listItems: (playlistId: string, filters: PlaylistFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.page) params.set('page', filters.page.toString());
    if (filters.page_size) params.set('page_size', filters.page_size.toString());

    const query = params.toString();
    return apiClient<PlaylistItemListResponse>(
      `/api/playlists/${playlistId}/items${query ? `?${query}` : ''}`
    );
  },
};
