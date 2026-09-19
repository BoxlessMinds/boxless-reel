"""Tests for src.utils.artifact_parser, the Python port of the frontend's
artifact detection logic (youtube-transcript-ui/src/lib/artifacts.ts)."""

from src.utils.artifact_parser import (
    artifact_filename_for_document,
    parse_artifacts,
    render_artifact_as_markdown,
)


def fence(lang: str, body: str) -> str:
    return f"```{lang}\n{body}\n```"


class TestClassify:
    def test_mermaid_by_language(self) -> None:
        content = fence("mermaid", "graph TD;\nA-->B;")
        artifacts = parse_artifacts(content)
        assert len(artifacts) == 1
        assert artifacts[0].kind == "mermaid"

    def test_svg_by_language(self) -> None:
        content = fence("svg", "<svg></svg>")
        artifacts = parse_artifacts(content)
        assert artifacts[0].kind == "svg"

    def test_svg_by_sniffing_leading_tag(self) -> None:
        content = fence("", "<svg viewBox='0 0 10 10'></svg>")
        artifacts = parse_artifacts(content)
        assert artifacts[0].kind == "svg"

    def test_html_by_language(self) -> None:
        content = fence("html", "<div>hello</div>")
        artifacts = parse_artifacts(content)
        assert artifacts[0].kind == "html"

    def test_html_by_sniffing_doctype(self) -> None:
        content = fence("", "<!doctype html><html><body>hi</body></html>")
        artifacts = parse_artifacts(content)
        assert artifacts[0].kind == "html"

    def test_markdown_by_language(self) -> None:
        body = "# Heading\n\n" + "Some body text that is long enough.\n" * 15
        content = fence("markdown", body)
        artifacts = parse_artifacts(content)
        assert artifacts[0].kind == "markdown"

    def test_defaults_to_code(self) -> None:
        long_body = "\n".join(f"line {i}" for i in range(20))
        content = fence("python", long_body)
        artifacts = parse_artifacts(content)
        assert artifacts[0].kind == "code"


class TestShouldPromote:
    def test_html_always_promotes_even_if_tiny(self) -> None:
        content = fence("html", "<b>x</b>")
        assert len(parse_artifacts(content)) == 1

    def test_short_code_block_not_promoted(self) -> None:
        content = fence("python", "print('hi')")
        assert parse_artifacts(content) == []

    def test_code_block_promoted_by_line_count(self) -> None:
        long_body = "\n".join(f"x = {i}" for i in range(16))
        content = fence("python", long_body)
        artifacts = parse_artifacts(content)
        assert len(artifacts) == 1

    def test_code_block_promoted_by_char_count(self) -> None:
        long_body = "x" * 900
        content = fence("python", long_body)
        artifacts = parse_artifacts(content)
        assert len(artifacts) == 1

    def test_short_markdown_block_not_promoted(self) -> None:
        content = fence("markdown", "just a short line")
        assert parse_artifacts(content) == []


class TestTitleFor:
    def test_markdown_uses_first_heading(self) -> None:
        body = "# My Great Report\n\n" + "content line\n" * 15
        content = fence("markdown", body)
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "My Great Report"

    def test_markdown_without_heading_falls_back_to_label(self) -> None:
        body = "no heading here\n" * 15
        content = fence("markdown", body)
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "Document"

    def test_html_uses_title_tag(self) -> None:
        content = fence("html", "<html><head><title>Landing Page</title></head></html>")
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "Landing Page"

    def test_html_without_title_tag_falls_back_to_label(self) -> None:
        content = fence("html", "<div>no title here</div>")
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "HTML"

    def test_svg_uses_title_tag(self) -> None:
        content = fence("svg", "<svg><title>Bar Chart</title></svg>")
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "Bar Chart"

    def test_code_uses_leading_comment(self) -> None:
        body = "# Fetch user records\n" + "\n".join(f"x = {i}" for i in range(16))
        content = fence("python", body)
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "Fetch user records"

    def test_code_without_comment_falls_back_to_language_snippet(self) -> None:
        body = "\n".join(f"x = {i}" for i in range(16))
        content = fence("python", body)
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "Python snippet"

    def test_code_without_language_falls_back_to_label(self) -> None:
        body = "\n".join(f"x = {i}" for i in range(16))
        content = fence("", body)
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "Code"

    def test_mermaid_falls_back_to_label(self) -> None:
        content = fence("mermaid", "graph TD;\nA-->B;")
        artifacts = parse_artifacts(content)
        assert artifacts[0].title == "Diagram"


class TestParseArtifactsIndexing:
    def test_index_only_increments_for_promoted_blocks(self) -> None:
        small_snippet = fence("python", "print('hi')")  # not promoted
        big_html = fence("html", "<b>promoted</b>")  # promoted, index 0
        another_small = fence("bash", "ls")  # not promoted
        big_mermaid = fence("mermaid", "graph TD;\nA-->B;")  # promoted, index 1

        content = "\n\n".join([small_snippet, big_html, another_small, big_mermaid])
        artifacts = parse_artifacts(content)

        assert len(artifacts) == 2
        assert artifacts[0].kind == "html"
        assert artifacts[1].kind == "mermaid"

    def test_no_fences_returns_empty(self) -> None:
        assert parse_artifacts("just plain text, no code blocks") == []

    def test_multiline_body_preserved(self) -> None:
        content = fence("html", "<div>\n  <p>hi</p>\n</div>")
        artifacts = parse_artifacts(content)
        assert artifacts[0].content == "<div>\n  <p>hi</p>\n</div>"


class TestFilenameAndRendering:
    def test_filename_slugifies_title(self) -> None:
        content = fence("html", "<title>My Cool Landing Page!!</title><body></body>")
        artifact = parse_artifacts(content)[0]
        assert artifact_filename_for_document(artifact) == "my-cool-landing-page.md"

    def test_filename_falls_back_to_kind_when_title_has_no_slug_chars(self) -> None:
        content = fence("svg", "<svg><title>!!!</title></svg>")
        artifact = parse_artifacts(content)[0]
        assert artifact_filename_for_document(artifact) == "svg.md"

    def test_markdown_rendered_as_is(self) -> None:
        body = "# Report\n\n" + "content line\n" * 15
        content = fence("markdown", body)
        artifact = parse_artifacts(content)[0]
        assert render_artifact_as_markdown(artifact) == artifact.content

    def test_code_wrapped_with_title_header(self) -> None:
        body = "\n".join(f"x = {i}" for i in range(16))
        content = fence("python", body)
        artifact = parse_artifacts(content)[0]
        rendered = render_artifact_as_markdown(artifact)
        assert rendered.startswith(f"# {artifact.title}\n")
        assert "```python" in rendered
        assert body in rendered
