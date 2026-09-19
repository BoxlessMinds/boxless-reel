import { Link } from "react-router-dom";
import { MessageSquare, Clock, ChevronRight, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CrossChatSession } from "@/api/types";
import { formatRelativeTime } from "@/utils/formatters";

interface CrossChatSessionCardProps {
  session: CrossChatSession;
  onDelete: () => void;
}

export function CrossChatSessionCard({ session, onDelete }: CrossChatSessionCardProps) {
  const refs = session.referenced_sessions;
  const maxThumbnails = 3;
  const visibleRefs = refs.slice(0, maxThumbnails);
  const extraCount = refs.length - maxThumbnails;

  return (
    <div className="group flex items-center gap-4 rounded-xl border border-border bg-card p-4 shadow-sm hover:shadow-md hover:border-primary/30 transition-all animate-fade-in">
      {/* Stacked thumbnails */}
      <div className="relative flex-shrink-0" style={{ width: `${56 + (visibleRefs.length - 1) * 16}px`, height: '48px' }}>
        {visibleRefs.map((ref, index) => (
          <div
            key={ref.session_id}
            className="absolute h-12 w-14 overflow-hidden rounded-md border-2 border-card bg-muted"
            style={{
              left: `${index * 16}px`,
              zIndex: visibleRefs.length - index,
            }}
          >
            <img
              src={ref.thumbnail_url ?? "/placeholder.svg"}
              alt={ref.video_title}
              className="h-full w-full object-cover"
            />
          </div>
        ))}
        {extraCount > 0 && (
          <div
            className="absolute h-12 w-14 overflow-hidden rounded-md border-2 border-card bg-muted flex items-center justify-center"
            style={{
              left: `${visibleRefs.length * 16}px`,
              zIndex: 0,
            }}
          >
            <span className="text-xs font-medium text-muted-foreground">+{extraCount}</span>
          </div>
        )}
      </div>

      {/* Session info */}
      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-card-foreground line-clamp-1">
          {refs.map((r) => r.video_title).join(", ")}
        </h3>
        <div className="mt-1 flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <MessageSquare className="h-3.5 w-3.5" />
            {session.query_count} queries
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {formatRelativeTime(session.last_activity)}
          </span>
          <span className="text-xs">
            {refs.length} sessions
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={(e) => {
            e.preventDefault();
            onDelete();
          }}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link to={`/cross-chat/${session.id}`}>
            Resume
            <ChevronRight className="h-4 w-4 ml-1" />
          </Link>
        </Button>
      </div>
    </div>
  );
}
