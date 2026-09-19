import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useArtifacts } from "@/contexts/ArtifactContext";
import { artifactMeta } from "./artifactMeta";
import type { Artifact } from "@/types/artifacts";

interface ArtifactCardProps {
  artifact: Artifact;
}

/**
 * Inline card shown in place of a lifted code/html/svg/etc. block. Clicking it
 * opens the artifact in the side panel.
 */
export function ArtifactCard({ artifact }: ArtifactCardProps) {
  const { openArtifact, activeArtifact } = useArtifacts();
  const meta = artifactMeta(artifact.kind);
  const Icon = meta.icon;
  const isActive = activeArtifact?.id === artifact.id;

  const lineCount = artifact.content.split(/\r?\n/).length;
  const subtitle = [meta.label, `${lineCount} ${lineCount === 1 ? "line" : "lines"}`]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      onClick={() => openArtifact(artifact)}
      aria-label={`Open artifact: ${artifact.title}`}
      className={cn(
        "my-3 flex w-full items-center gap-3 rounded-lg border bg-background px-3 py-2.5 text-left transition-colors",
        "hover:bg-accent hover:border-primary/40",
        isActive ? "border-primary ring-1 ring-primary/30" : "border-border"
      )}
    >
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-muted">
        <Icon className="h-4 w-4 text-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{artifact.title}</p>
        <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
      </div>
      <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
    </button>
  );
}
