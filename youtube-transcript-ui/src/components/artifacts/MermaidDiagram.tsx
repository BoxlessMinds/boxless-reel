import { useEffect, useId, useRef, useState } from "react";
import { AlertCircle } from "lucide-react";

interface MermaidDiagramProps {
  code: string;
}

/**
 * Renders a Mermaid diagram. Mermaid is imported dynamically so it only loads
 * when an actual diagram artifact is opened.
 */
export function MermaidDiagram({ code }: MermaidDiagramProps) {
  const rawId = useId();
  const renderId = `mermaid-${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    setError(null);
    setSvg(null);

    const isDark = document.documentElement.classList.contains("dark");

    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: isDark ? "dark" : "default",
        });
        const { svg: rendered } = await mermaid.render(renderId, code);
        if (!cancelled.current) setSvg(rendered);
      } catch (err) {
        if (!cancelled.current) {
          setError(err instanceof Error ? err.message : "Failed to render diagram");
        }
      }
    })();

    return () => {
      cancelled.current = true;
    };
  }, [code, renderId]);

  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <div>
          <p className="font-medium">Could not render diagram</p>
          <p className="mt-1 text-xs opacity-80">{error}</p>
        </div>
      </div>
    );
  }

  if (!svg) {
    return <div className="text-sm text-muted-foreground">Rendering diagram…</div>;
  }

  return (
    <div
      className="mermaid-diagram flex justify-center [&>svg]:h-auto [&>svg]:max-w-full"
      // Mermaid output is generated from the diagram source with securityLevel "strict".
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
