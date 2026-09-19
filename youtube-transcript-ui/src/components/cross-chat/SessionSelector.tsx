import { useState } from "react";
import { Check, MessageSquare, Clock, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useSessions } from "@/hooks/useSessions";
import { formatRelativeTime } from "@/utils/formatters";
import type { Session } from "@/api/types";

interface SessionSelectorProps {
  onCreateSession: (sessionIds: string[]) => void;
  isLoading?: boolean;
}

export function SessionSelector({ onCreateSession, isLoading }: SessionSelectorProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const { data, isLoading: sessionsLoading } = useSessions();

  const sessions = data?.items ?? [];

  const toggleSession = (sessionId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) {
        next.delete(sessionId);
      } else {
        next.add(sessionId);
      }
      return next;
    });
  };

  const handleCreate = () => {
    if (selectedIds.size >= 2) {
      onCreateSession(Array.from(selectedIds));
    }
  };

  if (sessionsLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (sessions.length < 2) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        <p>You need at least 2 transcript chat sessions to create a cross-chat.</p>
        <p className="text-sm mt-1">Start chatting with transcripts first.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 max-h-[400px] overflow-y-auto pr-1">
        {sessions.map((session: Session) => {
          const isSelected = selectedIds.has(session.session_id);
          return (
            <button
              key={session.session_id}
              onClick={() => toggleSession(session.session_id)}
              className={cn(
                "flex items-center gap-3 rounded-lg border p-3 text-left transition-all",
                isSelected
                  ? "border-primary bg-primary/5 ring-1 ring-primary"
                  : "border-border bg-card hover:border-primary/30 hover:bg-accent/50"
              )}
            >
              <div className="relative h-12 w-20 flex-shrink-0 overflow-hidden rounded-md bg-muted">
                <img
                  src={session.thumbnail_url ?? "/placeholder.svg"}
                  alt={session.video_title}
                  className="h-full w-full object-cover"
                />
                {isSelected && (
                  <div className="absolute inset-0 flex items-center justify-center bg-primary/60">
                    <Check className="h-5 w-5 text-primary-foreground" />
                  </div>
                )}
              </div>

              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm text-card-foreground line-clamp-1">
                  {session.video_title}
                </p>
                <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <MessageSquare className="h-3 w-3" />
                    {session.query_count} queries
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatRelativeTime(session.last_activity)}
                  </span>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-border">
        <span className="text-sm text-muted-foreground">
          {selectedIds.size} session{selectedIds.size !== 1 ? "s" : ""} selected
          {selectedIds.size < 2 && " (select at least 2)"}
        </span>
        <Button
          onClick={handleCreate}
          disabled={selectedIds.size < 2 || isLoading}
        >
          {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Create Cross-Chat
        </Button>
      </div>
    </div>
  );
}
