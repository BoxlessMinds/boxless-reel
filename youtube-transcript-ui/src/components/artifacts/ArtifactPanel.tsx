import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Download, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { markdownComponents } from "@/lib/markdownComponents";
import { useArtifacts } from "@/contexts/ArtifactContext";
import { artifactFilename, artifactMeta } from "./artifactMeta";
import { CodeView } from "./CodeView";
import { MermaidDiagram } from "./MermaidDiagram";
import type { Artifact } from "@/types/artifacts";

const MIME_TYPES: Record<Artifact["kind"], string> = {
  code: "text/plain",
  html: "text/html",
  svg: "image/svg+xml",
  mermaid: "text/plain",
  markdown: "text/markdown",
};

/** Rendered preview for an artifact that supports one. */
function ArtifactPreview({ artifact }: { artifact: Artifact }) {
  switch (artifact.kind) {
    case "html":
      return (
        <iframe
          title={artifact.title}
          srcDoc={artifact.content}
          sandbox="allow-scripts"
          className="h-full w-full rounded-lg border border-border bg-white"
        />
      );
    case "svg":
      return (
        <div className="flex h-full items-center justify-center overflow-auto rounded-lg border border-border bg-white p-4">
          <iframe
            title={artifact.title}
            srcDoc={artifact.content}
            sandbox=""
            className="h-full w-full border-0"
          />
        </div>
      );
    case "mermaid":
      return (
        <div className="overflow-auto rounded-lg border border-border bg-background p-4">
          <MermaidDiagram code={artifact.content} />
        </div>
      );
    case "markdown":
      return (
        <div className="rounded-lg border border-border bg-background p-4 text-sm text-foreground">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {artifact.content}
          </ReactMarkdown>
        </div>
      );
    default:
      return null;
  }
}

export function ArtifactPanel() {
  const { activeArtifact, isOpen, closeArtifact } = useArtifacts();
  const [copied, setCopied] = useState(false);

  if (!isOpen || !activeArtifact) return null;

  const artifact = activeArtifact;
  const meta = artifactMeta(artifact.kind);
  const Icon = meta.icon;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(artifact.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy artifact:", err);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([artifact.content], { type: MIME_TYPES[artifact.kind] });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = artifactFilename(artifact);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const header = (
    <div className="flex items-center gap-2 border-b border-border px-4 py-3">
      <Icon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">{artifact.title}</p>
        <p className="text-xs text-muted-foreground">
          {meta.label}
          {artifact.language ? ` · ${artifact.language}` : ""}
        </p>
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={handleCopy}
        title={copied ? "Copied!" : "Copy"}
        aria-label="Copy artifact"
      >
        {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={handleDownload}
        title="Download"
        aria-label="Download artifact"
      >
        <Download className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={closeArtifact}
        title="Close"
        aria-label="Close artifact panel"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  );

  const codeView = <CodeView code={artifact.content} language={artifact.language} />;

  return (
    <>
      {/* Mobile backdrop — clicking it closes the panel. */}
      <div
        className="fixed inset-0 z-40 bg-black/40 lg:hidden"
        onClick={closeArtifact}
        aria-hidden="true"
      />
      <aside
        className={cn(
          "fixed right-0 top-0 z-50 flex h-screen w-full flex-col border-l border-border bg-card shadow-xl",
          "animate-in slide-in-from-right duration-300 lg:w-[40rem]"
        )}
        role="dialog"
        aria-label={`Artifact: ${artifact.title}`}
      >
        {header}
        {meta.hasPreview ? (
          <Tabs defaultValue="preview" className="flex min-h-0 flex-1 flex-col">
            <div className="border-b border-border px-4 py-2">
              <TabsList className="h-8">
                <TabsTrigger value="preview" className="text-xs">
                  Preview
                </TabsTrigger>
                <TabsTrigger value="code" className="text-xs">
                  Code
                </TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="preview" className="min-h-0 flex-1 overflow-auto p-4">
              <ArtifactPreview artifact={artifact} />
            </TabsContent>
            <TabsContent value="code" className="min-h-0 flex-1 overflow-hidden p-4">
              {codeView}
            </TabsContent>
          </Tabs>
        ) : (
          <div className="min-h-0 flex-1 overflow-hidden p-4">{codeView}</div>
        )}
      </aside>
    </>
  );
}
