import { cn } from "@/lib/utils";

interface TranscriptSegment {
  text: string;
  start: number;
  duration: number;
}

interface TranscriptViewerProps {
  segments: TranscriptSegment[];
  className?: string;
}

function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

export function TranscriptViewer({ segments, className }: TranscriptViewerProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card p-4 max-h-[500px] overflow-y-auto scrollbar-thin",
        className
      )}
    >
      <div className="space-y-4">
        {segments.map((segment, index) => (
          <div key={index} className="flex gap-3 animate-fade-in" style={{ animationDelay: `${index * 30}ms` }}>
            <button className="timestamp flex-shrink-0">
              [{formatTimestamp(segment.start)}]
            </button>
            <p className="text-foreground leading-relaxed">{segment.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
