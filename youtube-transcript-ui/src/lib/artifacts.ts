/**
 * Client-side extraction of artifacts from assistant markdown.
 *
 * We scan fenced code blocks and decide which ones are substantial enough to
 * be promoted into the artifact side panel. Small inline snippets are left in
 * the message so short examples stay readable inline.
 */

import type { Artifact, ArtifactKind, MessageSegment, ParsedMessage } from "@/types/artifacts";

/** Minimum line count for a plain code/markdown block to become an artifact. */
const MIN_PROMOTE_LINES = 15;
/** Minimum character count (alternative threshold for dense one-liners). */
const MIN_PROMOTE_CHARS = 800;

/** Fenced code block: ```lang\n ...body... ``` */
const FENCE_RE = /```([\w.+-]*)[ \t]*\r?\n([\s\S]*?)```/g;

const HTML_LANGS = new Set(["html", "htm"]);
const SVG_LANGS = new Set(["svg"]);
const MERMAID_LANGS = new Set(["mermaid", "mmd"]);
const MARKDOWN_LANGS = new Set(["markdown", "md"]);

function classify(language: string, body: string): ArtifactKind {
  const lang = language.toLowerCase();
  const trimmed = body.trimStart();

  if (MERMAID_LANGS.has(lang)) return "mermaid";
  if (SVG_LANGS.has(lang) || /^<svg[\s>]/i.test(trimmed)) return "svg";
  if (HTML_LANGS.has(lang) || /^<!doctype html|^<html[\s>]/i.test(trimmed)) return "html";
  if (MARKDOWN_LANGS.has(lang)) return "markdown";
  return "code";
}

/**
 * Whether a block should be lifted into the side panel. Visual artifacts
 * (html/svg/mermaid) always promote because they have a rendered preview;
 * code/markdown promote only when they are long enough to be worth a panel.
 */
function shouldPromote(kind: ArtifactKind, body: string): boolean {
  if (kind === "html" || kind === "svg" || kind === "mermaid") return true;
  const lineCount = body.split(/\r?\n/).length;
  return lineCount >= MIN_PROMOTE_LINES || body.length >= MIN_PROMOTE_CHARS;
}

const KIND_LABEL: Record<ArtifactKind, string> = {
  code: "Code",
  html: "HTML",
  svg: "SVG image",
  mermaid: "Diagram",
  markdown: "Document",
};

function titleFor(kind: ArtifactKind, language: string, body: string): string {
  // Prefer a meaningful name pulled from the content itself.
  if (kind === "markdown") {
    const heading = body.match(/^\s{0,3}#{1,6}\s+(.+?)\s*$/m);
    if (heading) return heading[1].trim();
  }
  if (kind === "svg") {
    const titleTag = body.match(/<title[^>]*>([^<]+)<\/title>/i);
    if (titleTag) return titleTag[1].trim();
  }
  if (kind === "html") {
    const titleTag = body.match(/<title[^>]*>([^<]+)<\/title>/i);
    if (titleTag) return titleTag[1].trim();
  }
  if (kind === "code") {
    // Use a leading comment as a label if present.
    const comment = body.match(/^\s*(?:\/\/|#|--|\/\*)\s*(.{3,60}?)\s*(?:\*\/)?\s*$/m);
    const label = comment?.[1]?.trim();
    if (label && !/^[-=*]+$/.test(label)) {
      return label.length > 48 ? `${label.slice(0, 48)}…` : label;
    }
    if (language) {
      return `${language.charAt(0).toUpperCase()}${language.slice(1)} snippet`;
    }
  }
  return KIND_LABEL[kind];
}

/**
 * Parse an assistant message into ordered text/artifact segments.
 *
 * @param content   Raw assistant markdown.
 * @param messageKey Stable per-message key used to build artifact ids
 *                   (typically the message index within the conversation).
 */
export function parseArtifacts(content: string, messageKey: string | number): ParsedMessage {
  const segments: MessageSegment[] = [];
  const artifacts: Artifact[] = [];

  let lastIndex = 0;
  let blockIndex = 0;
  let match: RegExpExecArray | null;

  FENCE_RE.lastIndex = 0;
  while ((match = FENCE_RE.exec(content)) !== null) {
    const [full, rawLang, rawBody] = match;
    const language = (rawLang || "").trim();
    const body = rawBody.replace(/\s+$/, "");
    const kind = classify(language, body);

    if (!shouldPromote(kind, body)) {
      // Leave the fence inline; it will be picked up by the next text segment.
      continue;
    }

    // Text before this artifact.
    const preceding = content.slice(lastIndex, match.index);
    if (preceding.trim()) {
      segments.push({ type: "text", value: preceding });
    } else if (preceding) {
      segments.push({ type: "text", value: preceding });
    }

    const artifact: Artifact = {
      id: `${messageKey}-${blockIndex}`,
      kind,
      title: titleFor(kind, language, body),
      language: language || null,
      content: body,
    };
    artifacts.push(artifact);
    segments.push({ type: "artifact", artifact });

    lastIndex = match.index + full.length;
    blockIndex += 1;
  }

  // Trailing text after the last artifact (or the whole message if none).
  const trailing = content.slice(lastIndex);
  if (trailing) {
    segments.push({ type: "text", value: trailing });
  }

  // Collapse to a single text segment when nothing was promoted.
  if (artifacts.length === 0) {
    return { segments: [{ type: "text", value: content }], artifacts: [] };
  }

  return { segments, artifacts };
}
