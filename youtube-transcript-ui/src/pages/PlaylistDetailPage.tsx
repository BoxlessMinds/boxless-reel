import { useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import {
  ArrowLeft,
  ArrowUpDown,
  ListVideo,
  Loader2,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Copy,
  FolderInput,
  Trash2,
  Link as LinkIcon,
  History,
} from "lucide-react";
import { toast } from "sonner";
import { PageContainer } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/ui/EmptyState";
import { PlanReviewDialog } from "@/components/PlanReviewDialog";
import { MovePlaylistDialog } from "@/components/MovePlaylistDialog";
import { usePlaylists, usePlaylistItems } from "@/hooks/usePlaylists";
import { useCreatePlan } from "@/hooks/usePlans";
import { formatDate } from "@/utils/formatters";
import { ApiError } from "@/api/client";
import type { Playlist, PlaylistItem, PlaylistItemAvailability, ReorderSortBy } from "@/api/types";

function availabilityBadgeVariant(availability: PlaylistItemAvailability) {
  switch (availability) {
    case "available":
      return "outline" as const;
    case "private":
    case "deleted":
      return "destructive" as const;
    default:
      return "secondary" as const;
  }
}

function ItemRow({ item }: { item: PlaylistItem }) {
  return (
    <TableRow>
      <TableCell className="text-muted-foreground">{item.position}</TableCell>
      <TableCell className="font-medium">{item.title ?? "(unavailable)"}</TableCell>
      <TableCell className="text-muted-foreground">{item.channel_title ?? "Unknown"}</TableCell>
      <TableCell>
        <Badge variant={availabilityBadgeVariant(item.availability)} className="capitalize">
          {item.availability}
        </Badge>
      </TableCell>
      <TableCell className="text-muted-foreground">
        {item.added_at ? formatDate(item.added_at) : "-"}
      </TableCell>
      <TableCell>
        <a
          href={`https://www.youtube.com/watch?v=${item.video_id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Watch
        </a>
      </TableCell>
    </TableRow>
  );
}

export default function PlaylistDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [page, setPage] = useState(1);
  const [createdPlanId, setCreatedPlanId] = useState<string | null>(null);
  const [addUrlsInput, setAddUrlsInput] = useState("");
  const [watchedBeforeInput, setWatchedBeforeInput] = useState("");
  const [isMoveOpen, setIsMoveOpen] = useState(false);
  const [sortByInput, setSortByInput] = useState<ReorderSortBy>("title");

  const statePlaylist = (location.state as { playlist?: Playlist } | null)?.playlist;
  // Fall back to the list cache (e.g. on a direct URL load / refresh where nav state is gone).
  const { data: listData } = usePlaylists({ page: 1, page_size: 100 });
  const playlist = listData?.items.find((p) => p.id === id) ?? statePlaylist;

  const { data, isLoading, error } = usePlaylistItems(id!, { page, page_size: 20 });
  const createPlanMutation = useCreatePlan();

  const items = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;

  const handleDedupe = async () => {
    if (!id) return;
    try {
      const plan = await createPlanMutation.mutateAsync({ kind: "dedupe", playlist_id: id });
      setCreatedPlanId(plan.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to create dedupe plan");
    }
  };

  const handlePurgeUnavailable = async () => {
    if (!id) return;
    try {
      const plan = await createPlanMutation.mutateAsync({
        kind: "purge_unavailable",
        playlist_id: id,
        mode: "deleted",
      });
      setCreatedPlanId(plan.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to create purge plan");
    }
  };

  const handlePurgeWatched = async () => {
    if (!id) return;
    try {
      const plan = await createPlanMutation.mutateAsync({
        kind: "purge_watched",
        playlist_id: id,
        watched_before: watchedBeforeInput.trim() === "" ? null : watchedBeforeInput,
      });
      setCreatedPlanId(plan.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to create purge-watched plan");
    }
  };

  const handleReorder = async () => {
    if (!id) return;
    try {
      const plan = await createPlanMutation.mutateAsync({
        kind: "reorder",
        playlist_id: id,
        sort_by: sortByInput,
      });
      setCreatedPlanId(plan.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to create reorder plan");
    }
  };

  const handleAddByUrl = async () => {
    if (!id) return;
    const urls = addUrlsInput
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    if (urls.length === 0) {
      toast.error("Paste at least one YouTube URL or video ID");
      return;
    }
    try {
      const plan = await createPlanMutation.mutateAsync({
        kind: "add_url",
        urls,
        target_playlist_id: id,
        target_title: null,
      });
      setCreatedPlanId(plan.id);
      setAddUrlsInput("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to create add-by-url plan");
    }
  };

  return (
    <PageContainer>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <Button variant="ghost" onClick={() => navigate(-1)} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={handleDedupe}
              disabled={createPlanMutation.isPending}
            >
              <Copy className="h-4 w-4" />
              Dedupe
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={handlePurgeUnavailable}
              disabled={createPlanMutation.isPending}
            >
              <Trash2 className="h-4 w-4" />
              Purge unavailable
            </Button>
            <Input
              type="date"
              className="h-9 w-36"
              value={watchedBeforeInput}
              onChange={(e) => setWatchedBeforeInput(e.target.value)}
              aria-label="Purge watched before date (optional)"
            />
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={handlePurgeWatched}
              disabled={createPlanMutation.isPending}
            >
              <History className="h-4 w-4" />
              Purge watched
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => setIsMoveOpen(true)}
              disabled={createPlanMutation.isPending}
            >
              <FolderInput className="h-4 w-4" />
              Move to...
            </Button>
            <Select
              value={sortByInput}
              onValueChange={(value) => setSortByInput(value as ReorderSortBy)}
              disabled={createPlanMutation.isPending}
            >
              <SelectTrigger className="h-9 w-36" aria-label="Reorder by">
                <SelectValue placeholder="Reorder by..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="title">Title</SelectItem>
                <SelectItem value="channel">Channel</SelectItem>
                <SelectItem value="published">Published</SelectItem>
                <SelectItem value="added">Added</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={handleReorder}
              disabled={createPlanMutation.isPending}
            >
              <ArrowUpDown className="h-4 w-4" />
              Reorder
            </Button>
          </div>
        </div>

        {/* Playlist Info */}
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            {playlist?.title ?? "Playlist"}
          </h1>
          <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-muted-foreground">
            {playlist && (
              <>
                <span className="capitalize">{playlist.privacy_status}</span>
                <span>{playlist.item_count} items</span>
                {playlist.duplicate_count > 0 && (
                  <Badge variant="destructive">
                    {playlist.duplicate_count} dupe{playlist.duplicate_count !== 1 ? "s" : ""}
                  </Badge>
                )}
                {playlist.unavailable_count > 0 && (
                  <Badge variant="destructive">{playlist.unavailable_count} unavailable</Badge>
                )}
                <span>Last synced {formatDate(playlist.last_synced_at)}</span>
              </>
            )}
          </div>
        </div>

        {/* Add by URL */}
        <Card>
          <CardContent className="space-y-3 pt-6">
            <div className="flex items-center gap-2 text-sm font-medium">
              <LinkIcon className="h-4 w-4" />
              Add by URL
            </div>
            <Textarea
              placeholder={
                "Paste one YouTube URL (or video ID) per line, e.g.\n" +
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ\n" +
                "https://youtu.be/dQw4w9WgXcQ\n\n" +
                "Or paste a single playlist URL (list=...) to copy its items in."
              }
              rows={4}
              value={addUrlsInput}
              onChange={(e) => setAddUrlsInput(e.target.value)}
            />
            <div className="flex justify-end">
              <Button
                size="sm"
                className="gap-2"
                onClick={handleAddByUrl}
                disabled={createPlanMutation.isPending || addUrlsInput.trim().length === 0}
              >
                <LinkIcon className="h-4 w-4" />
                Add to playlist
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="flex items-center justify-center gap-2 py-12 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load playlist items</span>
          </div>
        )}

        {/* Items Table */}
        {!isLoading && !error && items.length > 0 && (
          <>
            <Card>
              <CardContent className="pt-6">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[60px]">#</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Channel</TableHead>
                      <TableHead>Availability</TableHead>
                      <TableHead>Added</TableHead>
                      <TableHead className="w-[100px]">Link</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <ItemRow key={item.id} item={item} />
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground px-4">
                  Page {page} of {totalPages} ({total} items)
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                >
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </>
        )}

        {/* Empty State */}
        {!isLoading && !error && items.length === 0 && (
          <EmptyState
            icon={ListVideo}
            title="No items found"
            description="This playlist has no cached items yet. Try syncing playlists from the Playlists page."
          />
        )}
      </div>

      {id && (
        <MovePlaylistDialog
          open={isMoveOpen}
          onOpenChange={setIsMoveOpen}
          sourcePlaylistId={id}
          onCreated={(planId) => setCreatedPlanId(planId)}
        />
      )}

      {createdPlanId && (
        <PlanReviewDialog planId={createdPlanId} onClose={() => setCreatedPlanId(null)} />
      )}
    </PageContainer>
  );
}
