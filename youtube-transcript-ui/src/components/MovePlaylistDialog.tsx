/**
 * "Move to..." builder -- creates a `kind: "move"` plan that moves a filtered
 * set of videos from the current playlist into a target playlist, then hands
 * the created plan id to the caller to open in the existing, generic
 * PlanReviewDialog.
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { usePlaylists } from '@/hooks/usePlaylists';
import { useCreatePlan } from '@/hooks/usePlans';
import { ApiError } from '@/api/client';

interface MovePlaylistDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourcePlaylistId: string;
  onCreated: (planId: string) => void;
}

export function MovePlaylistDialog({
  open,
  onOpenChange,
  sourcePlaylistId,
  onCreated,
}: MovePlaylistDialogProps) {
  const [targetPlaylistId, setTargetPlaylistId] = useState('');
  const [filterRegex, setFilterRegex] = useState('');

  const { data, isLoading } = usePlaylists({ page: 1, page_size: 100 });
  const createPlanMutation = useCreatePlan();

  const targetPlaylists = (data?.items ?? []).filter(
    (p) => p.is_owned && p.id !== sourcePlaylistId
  );

  useEffect(() => {
    if (!open) {
      setTargetPlaylistId('');
      setFilterRegex('');
    }
  }, [open]);

  const handleSubmit = async () => {
    if (!targetPlaylistId) {
      toast.error('Select a target playlist');
      return;
    }

    try {
      const plan = await createPlanMutation.mutateAsync({
        kind: 'move',
        source_playlist_id: sourcePlaylistId,
        target_playlist_id: targetPlaylistId,
        filter_regex: filterRegex.trim() ? filterRegex.trim() : null,
      });
      onOpenChange(false);
      onCreated(plan.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to create move plan');
    }
  };

  const isSubmitting = createPlanMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Move to...</DialogTitle>
          <DialogDescription>
            Move a filtered set of videos out of this playlist and into another one you own.
            Each moved video costs 100 units (a paired insert into the target, then a delete from
            here). Generates a plan you can review before anything changes on YouTube.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Target playlist</Label>
            {isLoading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <Select
                value={targetPlaylistId}
                onValueChange={setTargetPlaylistId}
                disabled={isSubmitting}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Choose a playlist you own" />
                </SelectTrigger>
                <SelectContent>
                  {targetPlaylists.map((playlist) => (
                    <SelectItem key={playlist.id} value={playlist.id}>
                      {playlist.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="move-filter-regex">Filter (optional)</Label>
            <Input
              id="move-filter-regex"
              value={filterRegex}
              onChange={(e) => setFilterRegex(e.target.value)}
              placeholder="Regex, e.g. ^Ep\."
              disabled={isSubmitting}
            />
            <p className="text-xs text-muted-foreground">
              Only move items whose title matches this pattern. Leave blank to move everything.
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
