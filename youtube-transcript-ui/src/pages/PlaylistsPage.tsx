import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ListVideo, Loader2, AlertCircle, ChevronLeft, ChevronRight, RefreshCw, Plus, ListPlus } from "lucide-react";
import { toast } from "sonner";
import { PageContainer } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/ui/EmptyState";
import { PlanReviewDialog } from "@/components/PlanReviewDialog";
import { CopyPlaylistDialog } from "@/components/CopyPlaylistDialog";
import { usePlaylists, useSyncPlaylists } from "@/hooks/usePlaylists";
import { useCreatePlan } from "@/hooks/usePlans";
import { formatDate } from "@/utils/formatters";
import { ApiError } from "@/api/client";
import type { Playlist } from "@/api/types";

type PrivacyStatus = "private" | "unlisted" | "public";

interface CreatePlaylistPayload {
  title: string;
  description: string | null;
  privacy_status: PrivacyStatus;
}

function CreatePlaylistDialog({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: CreatePlaylistPayload) => void | Promise<void>;
  isSubmitting: boolean;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [privacyStatus, setPrivacyStatus] = useState<PrivacyStatus>("private");

  useEffect(() => {
    if (!open) {
      setTitle("");
      setDescription("");
      setPrivacyStatus("private");
    }
  }, [open]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      toast.error("Please enter a playlist title");
      return;
    }
    onSubmit({
      title: trimmedTitle,
      description: description.trim() ? description.trim() : null,
      privacy_status: privacyStatus,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create playlist</DialogTitle>
          <DialogDescription>
            Generates a plan you can review before it's created on YouTube.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="playlist-title">Title</Label>
            <Input
              id="playlist-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="My new playlist"
              disabled={isSubmitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="playlist-description">Description</Label>
            <Textarea
              id="playlist-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional"
              disabled={isSubmitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="playlist-privacy">Privacy</Label>
            <Select
              value={privacyStatus}
              onValueChange={(value) => setPrivacyStatus(value as PrivacyStatus)}
              disabled={isSubmitting}
            >
              <SelectTrigger id="playlist-privacy">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="private">Private</SelectItem>
                <SelectItem value="unlisted">Unlisted</SelectItem>
                <SelectItem value="public">Public</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                "Create"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PlaylistRow({ playlist, onOpen }: { playlist: Playlist; onOpen: (id: string, playlist: Playlist) => void }) {
  return (
    <TableRow className="cursor-pointer" onClick={() => onOpen(playlist.id, playlist)}>
      <TableCell className="font-medium">{playlist.title}</TableCell>
      <TableCell className="text-muted-foreground capitalize">{playlist.privacy_status}</TableCell>
      <TableCell>{playlist.item_count}</TableCell>
      <TableCell>
        {playlist.duplicate_count > 0 ? (
          <Badge variant="destructive">{playlist.duplicate_count} dupe{playlist.duplicate_count !== 1 ? "s" : ""}</Badge>
        ) : (
          <Badge variant="secondary">0</Badge>
        )}
      </TableCell>
      <TableCell>
        {playlist.unavailable_count > 0 ? (
          <Badge variant="destructive">{playlist.unavailable_count} unavailable</Badge>
        ) : (
          <Badge variant="secondary">0</Badge>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground">{formatDate(playlist.last_synced_at)}</TableCell>
    </TableRow>
  );
}

export default function PlaylistsPage() {
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCopyOpen, setIsCopyOpen] = useState(false);
  const [createdPlanId, setCreatedPlanId] = useState<string | null>(null);
  const navigate = useNavigate();

  const { data, isLoading, error } = usePlaylists({ page, page_size: 20 });
  const syncMutation = useSyncPlaylists();
  const createPlanMutation = useCreatePlan();

  const playlists = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;

  const handleOpen = (id: string, playlist: Playlist) =>
    navigate(`/playlists/${id}`, { state: { playlist } });

  const handleSync = () => {
    syncMutation.mutate(undefined, {
      onSuccess: (result) => {
        toast.success(
          `Synced ${result.playlists_synced} playlist${result.playlists_synced !== 1 ? "s" : ""} (${result.items_synced} items)`
        );
        setPage(1);
      },
      onError: (err) => {
        toast.error(err instanceof ApiError ? err.message : "Failed to sync playlists");
      },
    });
  };

  const handleCreatePlaylist = async (payload: CreatePlaylistPayload) => {
    try {
      const plan = await createPlanMutation.mutateAsync({ kind: "create", ...payload });
      setIsCreateOpen(false);
      setCreatedPlanId(plan.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to create playlist plan");
    }
  };

  return (
    <PageContainer>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Playlists</h1>
            <p className="text-muted-foreground mt-1">
              {total} playlist{total !== 1 ? "s" : ""} synced
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setIsCreateOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Create Playlist
            </Button>
            <Button variant="outline" onClick={() => setIsCopyOpen(true)}>
              <ListPlus className="h-4 w-4 mr-2" />
              Copy from other playlists
            </Button>
            <Button onClick={handleSync} disabled={syncMutation.isPending}>
              {syncMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Sync Playlists
            </Button>
          </div>
        </div>

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
            <span>Failed to load playlists</span>
          </div>
        )}

        {/* Playlists Table */}
        {!isLoading && !error && playlists.length > 0 && (
          <>
            <Card>
              <CardContent className="pt-6">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Title</TableHead>
                      <TableHead>Privacy</TableHead>
                      <TableHead>Items</TableHead>
                      <TableHead>Duplicates</TableHead>
                      <TableHead>Unavailable</TableHead>
                      <TableHead>Last Synced</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {playlists.map((playlist) => (
                      <PlaylistRow key={playlist.id} playlist={playlist} onOpen={handleOpen} />
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
                  Page {page} of {totalPages}
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
        {!isLoading && !error && playlists.length === 0 && (
          <EmptyState
            icon={ListVideo}
            title="No playlists synced yet"
            description="Sync your YouTube playlists to see them here, including duplicate and unavailable item counts."
            action={
              <Button onClick={handleSync} disabled={syncMutation.isPending}>
                {syncMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4 mr-2" />
                )}
                Sync Playlists
              </Button>
            }
          />
        )}
      </div>

      <CreatePlaylistDialog
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        onSubmit={handleCreatePlaylist}
        isSubmitting={createPlanMutation.isPending}
      />

      <CopyPlaylistDialog
        open={isCopyOpen}
        onOpenChange={setIsCopyOpen}
        onCreated={(planId) => setCreatedPlanId(planId)}
      />

      {createdPlanId && (
        <PlanReviewDialog planId={createdPlanId} onClose={() => setCreatedPlanId(null)} />
      )}
    </PageContainer>
  );
}
