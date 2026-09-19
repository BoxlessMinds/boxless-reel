/**
 * Generic plan review + apply dialog for the plan/apply execution engine.
 *
 * Renders any plan's op list, status, and unit totals without assuming
 * anything about a particular `kind`/`op_type` — future stories that add
 * real plan-generation strategies (dedupe, purge, copy, ...) reuse this
 * dialog as-is and only need to produce a plan for it to review.
 */

import { useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Spinner } from '@/components/ui/Spinner';
import { usePlan, useApplyPlan, useQuota } from '@/hooks/usePlans';
import type { PlanOp, PlanOpStatus, PlanRemovalCandidate, PlanStatus } from '@/api/types';

interface PlanReviewDialogProps {
  planId: string;
  onClose: () => void;
}

const PLAN_STATUS_VARIANT: Record<PlanStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  applying: 'default',
  done: 'outline',
  failed: 'destructive',
};

const OP_STATUS_VARIANT: Record<PlanOpStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  done: 'outline',
  skipped: 'secondary',
  failed: 'destructive',
};

function JsonPreview({ value }: { value: Record<string, unknown> | null }) {
  if (!value || Object.keys(value).length === 0) {
    return <span className="text-muted-foreground">-</span>;
  }
  return (
    <pre className="max-w-xs overflow-x-auto whitespace-pre-wrap break-all rounded bg-muted p-2 text-xs">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

/** Extracts a dedupe/purge_unavailable plan's dry-run removal list from its
 * opaque `params`, if present -- see `Plan.params` (backend). */
function getRemovals(params: Record<string, unknown> | null): PlanRemovalCandidate[] | null {
  if (!params || !Array.isArray(params.removals)) return null;
  return params.removals as PlanRemovalCandidate[];
}

/** Extracts a copy plan's collision warnings from its opaque `params`
 * -- always an array (possibly empty) when present -- see `Plan.params`. */
function getWarnings(params: Record<string, unknown> | null): string[] {
  if (!params || !Array.isArray(params.warnings)) return [];
  return params.warnings as string[];
}

function WarningsList({ warnings }: { warnings: string[] }) {
  return (
    <Alert>
      <AlertTriangle className="h-4 w-4" />
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-4">
          {warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function RemovalsList({ removals }: { removals: PlanRemovalCandidate[] }) {
  if (removals.length === 0) {
    return (
      <div className="rounded-md border px-3 py-4 text-center text-sm text-muted-foreground">
        Nothing slated for removal.
      </div>
    );
  }
  return (
    <div className="rounded-md border">
      <div className="border-b bg-muted/50 px-3 py-2 text-xs font-medium text-muted-foreground">
        Items to remove ({removals.length})
      </div>
      <ScrollArea className="max-h-40">
        <div className="divide-y">
          {removals.map((removal) => (
            <div
              key={removal.sequence}
              className="flex items-center justify-between gap-4 px-3 py-2 text-sm"
            >
              <span className="truncate">{removal.title ?? '(untitled)'}</span>
              <span className="shrink-0 text-xs text-muted-foreground">#{removal.position}</span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}

function OpRow({ op }: { op: PlanOp }) {
  return (
    <div className="grid grid-cols-[auto_1fr_auto] gap-x-4 gap-y-1 border-b py-3 text-sm last:border-b-0">
      <div className="font-mono text-muted-foreground">#{op.sequence}</div>
      <div className="font-medium">{op.op_type}</div>
      <Badge variant={OP_STATUS_VARIANT[op.status]}>{op.status}</Badge>

      <div className="col-start-2 col-end-4 text-xs text-muted-foreground">
        estimated {op.estimated_units} units
        {op.actual_units !== null && <> - actual {op.actual_units} units</>}
        {op.depends_on_sequence !== null && <> - depends on #{op.depends_on_sequence}</>}
      </div>

      {op.error_message && (
        <Alert variant="destructive" className="col-start-2 col-end-4 py-2">
          <AlertDescription className="text-xs">{op.error_message}</AlertDescription>
        </Alert>
      )}

      {(op.payload || op.result) && (
        <div className="col-start-2 col-end-4 flex flex-wrap gap-4">
          {op.payload && (
            <div>
              <div className="mb-1 text-xs text-muted-foreground">payload</div>
              <JsonPreview value={op.payload} />
            </div>
          )}
          {op.result && (
            <div>
              <div className="mb-1 text-xs text-muted-foreground">result</div>
              <JsonPreview value={op.result} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PlanReviewDialog({ planId, onClose }: PlanReviewDialogProps) {
  const [budgetInput, setBudgetInput] = useState('');
  const { data: plan, isLoading: isPlanLoading } = usePlan(planId);
  const { data: quota, isLoading: isQuotaLoading } = useQuota();
  const applyPlan = useApplyPlan();

  const unspentEstimate = plan ? plan.total_estimated_units - plan.total_actual_units : 0;
  const exceedsQuota = !!quota && unspentEstimate > quota.remaining;
  const canApply = !!plan && (plan.status === 'pending' || plan.status === 'applying');
  const removals = plan ? getRemovals(plan.params) : null;
  const warnings = plan ? getWarnings(plan.params) : [];

  const handleApply = async () => {
    const parsedBudget = budgetInput.trim() === '' ? undefined : Number(budgetInput);
    if (parsedBudget !== undefined && (!Number.isFinite(parsedBudget) || parsedBudget < 0)) {
      toast.error('Budget units must be a non-negative number');
      return;
    }

    try {
      await applyPlan.mutateAsync({ planId, budgetUnits: parsedBudget ?? null });
      toast.success('Plan applied');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to apply plan');
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Plan review
            {plan && <Badge variant={PLAN_STATUS_VARIANT[plan.status]}>{plan.status}</Badge>}
          </DialogTitle>
          <DialogDescription>
            {plan ? `Kind: ${plan.kind}` : 'Loading plan...'}
          </DialogDescription>
        </DialogHeader>

        {isPlanLoading && (
          <div className="flex items-center justify-center py-8">
            <Spinner />
          </div>
        )}

        {plan && (
          <>
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <div>
                Estimated units: <span className="font-medium">{plan.total_estimated_units}</span>
              </div>
              <div>
                Actual units: <span className="font-medium">{plan.total_actual_units}</span>
              </div>
              <div>
                Remaining quota:{' '}
                <span className="font-medium">
                  {isQuotaLoading ? '...' : (quota?.remaining ?? '-')}
                </span>
              </div>
            </div>

            {exceedsQuota && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  This plan's remaining estimated cost ({unspentEstimate} units) exceeds the
                  remaining daily quota ({quota?.remaining} units). Applying may halt partway
                  through.
                </AlertDescription>
              </Alert>
            )}

            {removals && <RemovalsList removals={removals} />}

            {warnings.length > 0 && <WarningsList warnings={warnings} />}

            <ScrollArea className="max-h-80 rounded-md border px-3">
              {plan.ops.length === 0 ? (
                <div className="py-6 text-center text-sm text-muted-foreground">No ops in this plan.</div>
              ) : (
                plan.ops.map((op) => <OpRow key={op.id} op={op} />)
              )}
            </ScrollArea>

            {canApply && (
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <Label htmlFor="budget-units">Budget units (optional)</Label>
                  <Input
                    id="budget-units"
                    type="number"
                    min={0}
                    placeholder="Use server default"
                    value={budgetInput}
                    onChange={(e) => setBudgetInput(e.target.value)}
                  />
                </div>
              </div>
            )}
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          {canApply && (
            <Button onClick={handleApply} disabled={applyPlan.isPending}>
              {applyPlan.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Applying...
                </>
              ) : (
                'Apply'
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
