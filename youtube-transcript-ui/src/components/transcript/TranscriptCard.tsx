import { Link } from "react-router-dom";
import { Clock, ChevronRight, Globe, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface TranscriptCardProps {
  id: string;
  videoId: string;
  title: string;
  channelName: string;
  thumbnailUrl: string;
  duration: string;
  language: string;
  createdAt: string;
  variant?: "grid" | "list";
}

export function TranscriptCard({
  id,
  videoId,
  title,
  channelName,
  thumbnailUrl,
  duration,
  language,
  createdAt,
  variant = "list",
}: TranscriptCardProps) {
  if (variant === "grid") {
    return (
      <Link
        to={`/transcripts/${id}`}
        className="group block rounded-xl border border-border bg-card overflow-hidden shadow-sm hover:shadow-md hover:border-primary/30 transition-all animate-fade-in"
      >
        <div className="aspect-video relative overflow-hidden bg-muted">
          <img
            src={thumbnailUrl}
            alt={title}
            className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
          <div className="absolute bottom-2 right-2 rounded bg-foreground/80 px-1.5 py-0.5 text-xs font-mono text-background">
            {duration}
          </div>
        </div>
        <div className="p-4">
          <h3 className="font-medium text-card-foreground line-clamp-2 group-hover:text-primary transition-colors">
            {title}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{channelName}</p>
          <div className="mt-2 flex items-center justify-between">
            <p className="text-xs text-muted-foreground">{createdAt}</p>
            <a
              href={`https://www.youtube.com/watch?v=${videoId}`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-muted-foreground hover:text-primary transition-colors"
              title="Watch on YouTube"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          </div>
        </div>
      </Link>
    );
  }

  return (
    <Link
      to={`/transcripts/${id}`}
      className="group flex items-center gap-4 rounded-xl border border-border bg-card p-4 shadow-sm hover:shadow-md hover:border-primary/30 transition-all animate-fade-in"
    >
      <div className="relative h-20 w-36 flex-shrink-0 overflow-hidden rounded-lg bg-muted">
        <img
          src={thumbnailUrl}
          alt={title}
          className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-300"
        />
        <div className="absolute bottom-1 right-1 rounded bg-foreground/80 px-1.5 py-0.5 text-xs font-mono text-background">
          {duration}
        </div>
      </div>

      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-card-foreground line-clamp-1 group-hover:text-primary transition-colors">
          {title}
        </h3>
        <div className="mt-1 flex items-center gap-3 text-sm text-muted-foreground">
          <span>{channelName}</span>
          <span className="flex items-center gap-1">
            <Globe className="h-3 w-3" />
            {language}
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">Added: {createdAt}</p>
      </div>

      <a
        href={`https://www.youtube.com/watch?v=${videoId}`}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className="text-muted-foreground hover:text-primary transition-colors flex-shrink-0"
        title="Watch on YouTube"
      >
        <ExternalLink className="h-4 w-4" />
      </a>
      <ChevronRight className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
    </Link>
  );
}
