/**
 * TanStack Query hooks for playlist operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { playlistsApi, type PlaylistFilters } from '@/api/playlists';

// Query key factory for type-safe cache invalidation
export const playlistKeys = {
  all: ['playlists'] as const,
  lists: () => [...playlistKeys.all, 'list'] as const,
  list: (filters: PlaylistFilters) => [...playlistKeys.lists(), filters] as const,
  items: (playlistId: string) => [...playlistKeys.all, 'items', playlistId] as const,
  itemsList: (playlistId: string, filters: PlaylistFilters) =>
    [...playlistKeys.items(playlistId), filters] as const,
};

/**
 * Fetch a list of cached playlists with pagination.
 */
export function usePlaylists(filters: PlaylistFilters = {}) {
  return useQuery({
    queryKey: playlistKeys.list(filters),
    queryFn: () => playlistsApi.list(filters),
  });
}

/**
 * Fetch the paginated item list for a single playlist.
 */
export function usePlaylistItems(playlistId: string, filters: PlaylistFilters = {}) {
  return useQuery({
    queryKey: playlistKeys.itemsList(playlistId, filters),
    queryFn: () => playlistsApi.listItems(playlistId, filters),
    enabled: !!playlistId,
  });
}

/**
 * Trigger a full re-sync of the current user's owned playlists.
 */
export function useSyncPlaylists() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: playlistsApi.sync,
    onSuccess: () => {
      // Invalidate all playlist lists to refetch updated counts
      queryClient.invalidateQueries({ queryKey: playlistKeys.lists() });
    },
  });
}
