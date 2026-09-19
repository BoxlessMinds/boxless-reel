import { Clock, Globe, ExternalLink, FileText } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { Citation } from "@/api/types";

interface CitationBadgeProps {
  citation: Citation;
  onTimestampClick?: (startTime: number) => void;
}

export function CitationBadge({ citation, onTimestampClick }: CitationBadgeProps) {
  if (citation.source_type === 'transcript') {
    return (
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
              onClick={() => {
                if (onTimestampClick && citation.start_time !== undefined) {
                  onTimestampClick(citation.start_time);
                }
              }}
            >
              <Clock className="h-3 w-3" />
              {citation.timestamp_formatted}
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            <p className="text-xs">{citation.text}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // Document citation
  if (citation.source_type === 'document') {
    const displayName = citation.document_name || 'Document';
    const pageInfo = citation.page_number ? ` p.${citation.page_number}` : '';

    return (
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 cursor-default">
              <FileText className="h-3 w-3" />
              <span className="max-w-[150px] truncate">
                {displayName}{pageInfo}
              </span>
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            <p className="font-medium text-xs">{citation.document_name}</p>
            {citation.page_number && (
              <p className="text-xs text-muted-foreground">Page {citation.page_number}</p>
            )}
            <p className="text-xs mt-1">{citation.text}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // Web citation
  return (
    <TooltipProvider delayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 transition-colors"
          >
            <Globe className="h-3 w-3" />
            <span className="max-w-[150px] truncate">
              {citation.title || citation.url}
            </span>
            <ExternalLink className="h-3 w-3 flex-shrink-0" />
          </a>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <p className="text-xs">{citation.text}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
