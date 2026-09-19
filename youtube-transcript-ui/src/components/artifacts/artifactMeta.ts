import { Code2, FileCode2, FileText, Image, Workflow, type LucideIcon } from "lucide-react";
import type { Artifact, ArtifactKind } from "@/types/artifacts";

interface ArtifactMeta {
  icon: LucideIcon;
  label: string;
  /** Whether this kind has a rendered preview tab in the panel. */
  hasPreview: boolean;
}

const META: Record<ArtifactKind, ArtifactMeta> = {
  code: { icon: Code2, label: "Code", hasPreview: false },
  html: { icon: FileCode2, label: "HTML", hasPreview: true },
  svg: { icon: Image, label: "SVG", hasPreview: true },
  mermaid: { icon: Workflow, label: "Diagram", hasPreview: true },
  markdown: { icon: FileText, label: "Document", hasPreview: true },
};

export function artifactMeta(kind: ArtifactKind): ArtifactMeta {
  return META[kind];
}

/** Suggested download filename for an artifact, derived from its title. */
export function artifactFilename(artifact: Artifact): string {
  const ext: Record<ArtifactKind, string> = {
    code: artifact.language ? extensionForLanguage(artifact.language) : "txt",
    html: "html",
    svg: "svg",
    mermaid: "mmd",
    markdown: "md",
  };
  const slug = slugify(artifact.title);
  return `${slug || artifact.kind}.${ext[artifact.kind]}`;
}

/** Convert a title into a filesystem-safe slug for use as a filename stem. */
function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/, "");
}

function extensionForLanguage(language: string): string {
  const map: Record<string, string> = {
    javascript: "js",
    js: "js",
    typescript: "ts",
    ts: "ts",
    tsx: "tsx",
    jsx: "jsx",
    python: "py",
    py: "py",
    bash: "sh",
    shell: "sh",
    sh: "sh",
    json: "json",
    yaml: "yml",
    yml: "yml",
    sql: "sql",
    css: "css",
    java: "java",
    go: "go",
    rust: "rs",
    rs: "rs",
    c: "c",
    cpp: "cpp",
    csharp: "cs",
    cs: "cs",
    ruby: "rb",
    rb: "rb",
    php: "php",
  };
  return map[language.toLowerCase()] ?? "txt";
}
