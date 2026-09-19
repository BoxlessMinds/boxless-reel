import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { User, Bot, Copy, Check, Download } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "@/api/types";
import { CitationBadge } from "./CitationBadge";
import { markdownComponents } from "@/lib/markdownComponents";
import { parseArtifacts } from "@/lib/artifacts";
import { ArtifactCard } from "@/components/artifacts/ArtifactCard";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[] | null;
  onSeekTo?: (time: number) => void;
  /** Stable key (e.g. message index) used to derive artifact ids. */
  messageKey?: string | number;
}

export function ChatMessage({ role, content, citations, onSeekTo, messageKey = 0 }: ChatMessageProps) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);

  // Lift substantial code/html/svg/mermaid/markdown blocks into artifact cards.
  // Derived from the (already persisted) message content, so artifacts reappear
  // whenever a saved session is reopened. User messages are never parsed.
  const parsed = useMemo(
    () => (isUser ? null : parseArtifacts(content, messageKey)),
    [isUser, content, messageKey]
  );

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, "");
    const link = document.createElement("a");
    link.href = url;
    link.download = `response-${timestamp}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className={cn(
        "flex gap-3 animate-fade-in",
        isUser && "flex-row-reverse"
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-full flex-shrink-0",
          isUser ? "bg-primary" : "bg-accent"
        )}
      >
        {isUser ? (
          <User className="h-4 w-4 text-primary-foreground" />
        ) : (
          <Bot className="h-4 w-4 text-accent-foreground" />
        )}
      </div>

      <div
        className={cn(
          "group relative max-w-[80%] rounded-xl px-4 py-3",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-card border border-border"
        )}
      >
        {/* Action buttons for assistant messages */}
        {!isUser && (
          <div className="absolute -top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={handleCopy}
                    className="p-1.5 rounded-md bg-background border border-border hover:bg-accent transition-colors"
                    aria-label="Copy message"
                  >
                    {copied ? (
                      <Check className="h-3.5 w-3.5 text-green-600" />
                    ) : (
                      <Copy className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top">
                  <p>{copied ? "Copied!" : "Copy"}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={handleDownload}
                    className="p-1.5 rounded-md bg-background border border-border hover:bg-accent transition-colors"
                    aria-label="Download message"
                  >
                    <Download className="h-3.5 w-3.5 text-muted-foreground" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top">
                  <p>Download</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        )}

        {/* Message content */}
        {isUser ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="text-sm text-foreground">
            {parsed!.segments.map((segment, index) =>
              segment.type === "artifact" ? (
                <ArtifactCard key={index} artifact={segment.artifact} />
              ) : (
                <ReactMarkdown
                  key={index}
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents}
                >
                  {segment.value}
                </ReactMarkdown>
              )
            )}
          </div>
        )}

        {/* Citations */}
        {citations && citations.length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Sources:</p>
            <div className="flex flex-wrap gap-2">
              {citations.map((citation, index) => (
                <CitationBadge
                  key={index}
                  citation={citation}
                  onTimestampClick={onSeekTo}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
