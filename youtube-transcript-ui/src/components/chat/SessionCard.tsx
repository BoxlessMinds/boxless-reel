import { Link } from "react-router-dom";
import { MessageSquare, Clock, ChevronRight, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SessionCardProps {
  id: string;
  videoTitle: string;
  thumbnailUrl: string;
  queryCount: number;
  lastActivity: string;
  transcriptId: string;
  onDelete?: () => void;
}

export function SessionCard({
  id,
  videoTitle,
  thumbnailUrl,
  queryCount,
  lastActivity,
  transcriptId,
  onDelete,
}: SessionCardProps) {
  return (
    <div className="group flex items-center gap-4 rounded-xl border border-border bg-card p-4 shadow-sm hover:shadow-md hover:border-primary/30 transition-all animate-fade-in">
      <div className="relative h-16 w-28 flex-shrink-0 overflow-hidden rounded-lg bg-muted">
        <img
          src={thumbnailUrl}
          alt={videoTitle}
          className="h-full w-full object-cover"
        />
      </div>

      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-card-foreground line-clamp-1">
          {videoTitle}
        </h3>
        <div className="mt-1 flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <MessageSquare className="h-3.5 w-3.5" />
            {queryCount} queries
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {lastActivity}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={(e) => {
            e.preventDefault();
            onDelete?.();
          }}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link to={`/transcripts/${transcriptId}?tab=chat&session=${id}`}>
            Resume
            <ChevronRight className="h-4 w-4 ml-1" />
          </Link>
        </Button>
      </div>
    </div>
  );
}
