/**
 * Types for the chat "artifacts" feature.
 *
 * Artifacts are substantial, self-contained pieces of content (code, HTML,
 * SVG, Mermaid diagrams, or long-form markdown documents) that get lifted out
 * of an assistant message and shown in a dedicated side panel — similar to
 * Claude's artifacts. Detection is performed entirely on the client by parsing
 * the assistant's markdown, so artifacts are re-derived from the persisted
 * message content whenever a session is reopened.
 */

export type ArtifactKind = "code" | "html" | "svg" | "mermaid" | "markdown";

export interface Artifact {
  /** Stable id within a conversation: `${messageKey}-${blockIndex}`. */
  id: string;
  kind: ArtifactKind;
  /** Human-readable title shown on the card and panel header. */
  title: string;
  /** Source language for code artifacts (e.g. "python"); null otherwise. */
  language: string | null;
  /** Raw content of the artifact (code, html, svg, mermaid, or markdown). */
  content: string;
}

/** A piece of a parsed assistant message: either inline text or an artifact. */
export type MessageSegment =
  | { type: "text"; value: string }
  | { type: "artifact"; artifact: Artifact };

export interface ParsedMessage {
  /** Message content split into ordered text/artifact segments. */
  segments: MessageSegment[];
  /** All artifacts found in the message, in document order. */
  artifacts: Artifact[];
}
