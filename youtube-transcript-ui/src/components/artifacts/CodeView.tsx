import { useEffect, useState } from "react";
import "highlight.js/styles/github-dark.css";

interface CodeViewProps {
  code: string;
  /** Source language hint; falls back to auto-detection when unknown. */
  language?: string | null;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * Syntax-highlighted, read-only code block used for the "Code" view of an
 * artifact. highlight.js is imported dynamically so its weight is only paid
 * when a code artifact is actually opened. Uses a self-contained dark theme so
 * it looks consistent regardless of the app's light/dark mode.
 */
export function CodeView({ code, language }: CodeViewProps) {
  const [html, setHtml] = useState<string>(() => escapeHtml(code));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const hljs = (await import("highlight.js/lib/common")).default;
        const result =
          language && hljs.getLanguage(language)
            ? hljs.highlight(code, { language })
            : hljs.highlightAuto(code);
        if (!cancelled) setHtml(result.value);
      } catch {
        if (!cancelled) setHtml(escapeHtml(code));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, language]);

  return (
    <pre className="hljs h-full overflow-auto rounded-lg p-4 text-xs leading-relaxed">
      <code className="font-mono" dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  );
}
