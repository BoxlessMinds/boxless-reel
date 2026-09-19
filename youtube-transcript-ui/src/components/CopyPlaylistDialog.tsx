/**
 * "Copy from other playlists" builder — creates a `kind: "copy"` plan from a
 * multi-select of source playlists and a target (existing playlist or new
 * title), then hands the created plan id to the caller to open in the
 * existing, generic PlanReviewDialog.
 */

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { usePlaylists } from '@/hooks/usePlaylists';
import { useCreatePlan } from '@/hooks/usePlans';
import { ApiError } from '@/api/client';

type TargetMode = 'existing' | 'new';

interface CopyPlaylistDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (planId: string) => void;
}

export function CopyPlaylistDialog({ open, onOpenChange, onCreated }: CopyPlaylistDialogProps) {
  // youtube_playlist_id values, not local cache Playlist.id UUIDs -- source_playlist_ids is
  // resolved server-side against YouTube, unlike target_playlist_id (a local cache UUID below).
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [targetMode, setTargetMode] = useState<TargetMode>('new');
  const [targetPlaylistId, setTargetPlaylistId] = useState('');
  const [targetTitle, setTargetTitle] = useState('');
  const [filterRegex, setFilterRegex] = useState('');
  const [forceNew, setForceNew] = useState(false);

  const { data, isLoading } = usePlaylists({ page: 1, page_size: 100 });
  const createPlanMutation = useCreatePlan();

  const playlists = data?.items ?? [];
  const ownedPlaylists = playlists.filter((p) => p.is_owned);

  useEffect(() => {
    if (!open) {
      setSourceIds([]);
      setTargetMode('new');
      setTargetPlaylistId('');
      setTargetTitle('');
      setFilterRegex('');
      setForceNew(false);
    }
  }, [open]);

  const toggleSource = (id: string, checked: boolean) => {
    setSourceIds((prev) => (checked ? [...prev, id] : prev.filter((existing) => existing !== id)));
  };

  const handleSubmit = async () => {
    if (sourceIds.length === 0) {
      toast.error('Select at least one source playlist');
      return;
    }
    const trimmedTitle = targetTitle.trim();
    if (targetMode === 'existing' && !targetPlaylistId) {
      toast.error('Select a target playlist');
      return;
    }
    if (targetMode === 'new' && !trimmedTitle) {
      toast.error('Enter a title for the new playlist');
      return;
    }

    try {
      const plan = await createPlanMutation.mutateAsync({
        kind: 'copy',
        source_playlist_ids: sourceIds,
        target_playlist_id: targetMode === 'existing' ? targetPlaylistId : null,
        target_title: targetMode === 'new' ? trimmedTitle : null,
        filter_regex: filterRegex.trim() ? filterRegex.trim() : null,
        force_new: targetMode === 'new' ? forceNew : false,
      });
      onOpenChange(false);
      onCreated(plan.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to create copy plan');
    }
  };

  const isSubmitting = createPlanMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Copy from other playlists</DialogTitle>
          <DialogDescription>
            Build a new plan that unions items from the sources you pick below. Generates a plan
            you can review before anything changes on YouTube.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Source playlists</Label>
            {isLoading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ScrollArea className="h-40 rounded-md border">
                <div className="divide-y">
                  {playlists.map((playlist) => (
                    <label
                      key={playlist.id}
                      className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer"
                    >
                      <Checkbox
                        checked={sourceIds.includes(playlist.youtube_playlist_id)}
                        onCheckedChange={(checked) =>
                          toggleSource(playlist.youtube_playlist_id, checked === true)
                        }
                        disabled={isSubmitting}
                      />
                      <span className="truncate">{playlist.title}</span>
                    </label>
                  ))}
                  {playlists.length === 0 && (
                    <div className="px-3 py-4 text-center text-sm text-muted-foreground">
                      No playlists synced yet.
                    </div>
                  )}
                </div>
              </ScrollArea>
            )}
          </div>

          <div className="space-y-2">
            <Label>Target</Label>
            <RadioGroup
              value={targetMode}
              onValueChange={(value) => setTargetMode(value as TargetMode)}
              className="gap-3"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="new" id="target-new" disabled={isSubmitting} />
                <Label htmlFor="target-new" className="font-normal">
                  Create new playlist
                </Label>
              </div>
              {targetMode === 'new' && (
                <div className="ml-6 space-y-2">
                  <Input
                    value={targetTitle}
                    onChange={(e) => setTargetTitle(e.target.value)}
                    placeholder="New playlist title"
                    disabled={isSubmitting}
                  />
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={forceNew}
                      onCheckedChange={(checked) => setForceNew(checked === true)}
                      disabled={isSubmitting}
                    />
                    Create new even if a playlist with this title already exists
                  </label>
                </div>
              )}

              <div className="flex items-center gap-2">
                <RadioGroupItem value="existing" id="target-existing" disabled={isSubmitting} />
                <Label htmlFor="target-existing" className="font-normal">
                  Use existing playlist
                </Label>
              </div>
              {targetMode === 'existing' && (
                <div className="ml-6">
                  <Select
                    value={targetPlaylistId}
                    onValueChange={setTargetPlaylistId}
                    disabled={isSubmitting}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Choose a playlist you own" />
                    </SelectTrigger>
                    <SelectContent>
                      {ownedPlaylists.map((playlist) => (
                        <SelectItem key={playlist.id} value={playlist.id}>
                          {playlist.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </RadioGroup>
          </div>

          <div className="space-y-2">
            <Label htmlFor="copy-filter-regex">Filter (optional)</Label>
            <Input
              id="copy-filter-regex"
              value={filterRegex}
              onChange={(e) => setFilterRegex(e.target.value)}
              placeholder="Regex, e.g. ^Ep\."
              disabled={isSubmitting}
            />
            <p className="text-xs text-muted-foreground">
              Only include items whose title matches this pattern.
            </p>
          </div>
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
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Creating...
              </>
            ) : (
              'Create plan'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
