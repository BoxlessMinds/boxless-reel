"""Server-side extraction of chat "artifacts" from assistant markdown.

This is a behavioral port of youtube-transcript-ui/src/lib/artifacts.ts and
youtube-transcript-ui/src/components/artifacts/artifactMeta.ts (slugify).
Keep this module in sync by hand with those files when either changes -
there is no shared code path between the TypeScript frontend and this
Python backend.
"""

import re
from dataclasses import dataclass
from typing import Literal

ArtifactKind = Literal["code", "html", "svg", "mermaid", "markdown"]

# Minimum line count for a plain code/markdown block to become an artifact.
MIN_PROMOTE_LINES = 15
# Minimum character count (alternative threshold for dense one-liners).
MIN_PROMOTE_CHARS = 800

# Fenced code block: ```lang\n ...body... ```
FENCE_RE = re.compile(r"```([\w.+-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)

HTML_LANGS = {"html", "htm"}
SVG_LANGS = {"svg"}
MERMAID_LANGS = {"mermaid", "mmd"}
MARKDOWN_LANGS = {"markdown", "md"}

KIND_LABEL: dict[ArtifactKind, str] = {
    "code": "Code",
    "html": "HTML",
    "svg": "SVG image",
    "mermaid": "Diagram",
    "markdown": "Document",
}


@dataclass
class ParsedArtifact:
    """A single artifact promoted out of an assistant message."""

    kind: ArtifactKind
    title: str
    language: str | None
    content: str


def _classify(language: str, body: str) -> ArtifactKind:
    lang = language.lower()
    trimmed = body.lstrip()

    if lang in MERMAID_LANGS:
        return "mermaid"
    if lang in SVG_LANGS or re.match(r"<svg[\s>]", trimmed, re.IGNORECASE):
        return "svg"
    if lang in HTML_LANGS or re.match(r"<!doctype html|<html[\s>]", trimmed, re.IGNORECASE):
        return "html"
    if lang in MARKDOWN_LANGS:
        return "markdown"
    return "code"


def _should_promote(kind: ArtifactKind, body: str) -> bool:
    """Whether a block should be lifted out as a standalone artifact.

    Visual artifacts (html/svg/mermaid) always promote because they have a
    rendered preview; code/markdown promote only when long enough to be
    worth a document of their own.
    """
    if kind in ("html", "svg", "mermaid"):
        return True
    line_count = len(re.split(r"\r?\n", body))
    return line_count >= MIN_PROMOTE_LINES or len(body) >= MIN_PROMOTE_CHARS


def _title_for(kind: ArtifactKind, language: str, body: str) -> str:
    # Prefer a meaningful name pulled from the content itself.
    if kind == "markdown":
        heading = re.search(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", body, re.MULTILINE)
        if heading:
            return heading.group(1).strip()
    if kind in ("svg", "html"):
        title_tag = re.search(r"<title[^>]*>([^<]+)</title>", body, re.IGNORECASE)
        if title_tag:
            return title_tag.group(1).strip()
    if kind == "code":
        comment = re.search(
            r"^\s*(?://|#|--|/\*)\s*(.{3,60}?)\s*(?:\*/)?\s*$", body, re.MULTILINE
        )
        label = comment.group(1).strip() if comment else None
        if label and not re.fullmatch(r"[-=*]+", label):
            return f"{label[:48]}…" if len(label) > 48 else label
        if language:
            return f"{language[0].upper()}{language[1:]} snippet"
    return KIND_LABEL[kind]


def parse_artifacts(content: str) -> list[ParsedArtifact]:
    """Extract promoted artifacts from assistant markdown, in document order.

    Only fenced blocks that pass `_should_promote` are returned - this
    mirrors the frontend, where an artifact's positional index (used to
    build `Artifact.id`) only increments for promoted blocks. The index of
    an entry in the returned list is therefore the same "block index" the
    frontend would derive for the same message content.
    """
    artifacts: list[ParsedArtifact] = []
    for match in FENCE_RE.finditer(content):
        raw_lang, raw_body = match.group(1), match.group(2)
        language = (raw_lang or "").strip()
        body = re.sub(r"\s+$", "", raw_body)
        kind = _classify(language, body)

        if not _should_promote(kind, body):
            continue

        artifacts.append(
            ParsedArtifact(
                kind=kind,
                title=_title_for(kind, language, body),
                language=language or None,
                content=body,
            )
        )
    return artifacts


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    slug = slug.strip("-")
    return slug[:60].rstrip("-")


def artifact_filename_for_document(artifact: ParsedArtifact) -> str:
    """Suggested filename for an artifact saved into the document library.

    Saved artifacts are always normalized to Markdown, so this always
    returns a `.md` filename regardless of the artifact's original kind.
    """
    slug = _slugify(artifact.title)
    return f"{slug or artifact.kind}.md"


def render_artifact_as_markdown(artifact: ParsedArtifact) -> str:
    """Render an artifact as the Markdown text saved into the document library.

    Markdown artifacts are saved verbatim. Other kinds are wrapped in a
    fenced code block with a small title header, since the document
    library's storage/indexing pipeline only handles text/markdown content.
    """
    if artifact.kind == "markdown":
        return artifact.content

    subtitle = KIND_LABEL[artifact.kind]
    if artifact.language:
        subtitle = f"{subtitle} ({artifact.language})"
    fence_lang = artifact.language or artifact.kind

    return f"# {artifact.title}\n\n_Artifact type: {subtitle}_\n\n```{fence_lang}\n{artifact.content}\n```\n"
