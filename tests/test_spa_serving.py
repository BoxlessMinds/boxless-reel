"""Tests for serving the built frontend from a build folder."""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.main import register_frontend_routes

INDEX_HTML = "<html><body>index page</body></html>"
ASSET_JS = "console.log('asset');"
NESTED_TXT = "nested file contents"
OUTSIDE_MARKER = "MARKER-OUTSIDE-BUILD-FOLDER"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a build folder plus a marker file that sits outside it."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "subdir").mkdir()
    (dist / "index.html").write_text(INDEX_HTML)
    (dist / "favicon.svg").write_text("<svg></svg>")
    (dist / "assets" / "app.js").write_text(ASSET_JS)
    (dist / "subdir" / "nested.txt").write_text(NESTED_TXT)
    (tmp_path / "outside.txt").write_text(OUTSIDE_MARKER)
    (tmp_path / "dist-sibling").mkdir()
    (tmp_path / "dist-sibling" / "outside.txt").write_text(OUTSIDE_MARKER)
    return tmp_path


@pytest.fixture
def dist_dir(workspace: Path) -> Path:
    """Return the temporary build folder."""
    return workspace / "dist"


@pytest.fixture
def spa_app(dist_dir: Path) -> FastAPI:
    """Build an app with a health route and frontend routes for the temp folder."""
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check."""
        return {"status": "healthy"}

    register_frontend_routes(app, dist_dir)
    return app


@pytest.fixture
def spa_client(spa_app: FastAPI) -> Iterator[TestClient]:
    """Return a test client for the frontend app."""
    with TestClient(spa_app) as client:
        yield client


def raw_request(app: FastAPI, raw_target: str) -> tuple[int, str]:
    """
    Send a request whose target is passed to the app without normalisation.

    The path is percent-decoded the same way the ASGI server does before routing,
    so encoded dots and slashes reach the route as the server would deliver them.

    Args:
        app: The ASGI application
        raw_target: The request target exactly as it would appear on the wire

    Returns:
        Tuple of (status code, response body text)
    """
    path = unquote(raw_target)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": raw_target.encode("ascii"),
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }
    status = 0
    chunks: list[bytes] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    async def run() -> None:
        await app(scope, receive, send)

    asyncio.run(run())
    return status, b"".join(chunks).decode("utf-8", errors="replace")


def assert_no_outside_content(status: int, body: str) -> None:
    """Assert a response is index.html or a 404, and never the outside file."""
    assert OUTSIDE_MARKER not in body
    assert status in (200, 404)
    if status == 200:
        assert body == INDEX_HTML


def outside_paths(workspace: Path) -> list[str]:
    """Return absolute forms of the outside file, in posix and native style."""
    target = workspace / "outside.txt"
    return [target.as_posix(), str(target)]


class TestServesOnlyFilesInsideBuildFolder:
    """Requests must never return content from outside the build folder."""

    @pytest.mark.parametrize(
        "raw_target",
        [
            "/../outside.txt",
            "/../../outside.txt",
            "/assets/../../outside.txt",
            "/subdir/../../outside.txt",
            "/%2e%2e/outside.txt",
            "/%2E%2E/outside.txt",
            "/%2e%2e/%2e%2e/outside.txt",
            "/..%2foutside.txt",
            "/..%2Foutside.txt",
            "/%2e%2e%2foutside.txt",
            "/%2e%2e%2f%2e%2e%2foutside.txt",
            "/.%2e/outside.txt",
            "/%2e./outside.txt",
            "/..%5coutside.txt",
            "/%2e%2e%5coutside.txt",
            "/..\\outside.txt",
            "/..\\..\\outside.txt",
            "/..%c0%afoutside.txt",
            "/%252e%252e/outside.txt",
            "/%252e%252e%252foutside.txt",
            "/../dist-sibling/outside.txt",
            "/../dist/../outside.txt",
            "/..../outside.txt",
            "/.. /outside.txt",
            "/../outside.txt.",
            "/../outside.txt%20",
        ],
    )
    def test_relative_paths_stay_inside_build_folder(
        self, spa_app: FastAPI, raw_target: str
    ) -> None:
        """Relative paths in any encoding return index.html or 404."""
        assert_no_outside_content(*raw_request(spa_app, raw_target))

    def test_absolute_paths_stay_inside_build_folder(
        self, spa_app: FastAPI, workspace: Path
    ) -> None:
        """Absolute paths, with or without an extra leading slash, are not served."""
        for absolute in outside_paths(workspace):
            for prefix in ("/", "//", "///"):
                raw_target = prefix + absolute.lstrip("/")
                assert_no_outside_content(*raw_request(spa_app, raw_target))
            drive_style = "/" + absolute.replace("\\", "/")
            assert_no_outside_content(*raw_request(spa_app, drive_style))

    def test_encoded_absolute_paths_stay_inside_build_folder(
        self, spa_app: FastAPI, workspace: Path
    ) -> None:
        """Percent-encoded separators in an absolute path are not served."""
        absolute = (workspace / "outside.txt").as_posix()
        encoded = absolute.replace("/", "%2f").replace(":", "%3a")
        assert_no_outside_content(*raw_request(spa_app, "/" + encoded))
        assert_no_outside_content(*raw_request(spa_app, "//" + encoded))

    @pytest.mark.parametrize(
        "raw_target",
        [
            "/%00",
            "/index.html%00",
            "/..%00/outside.txt",
            "/../outside.txt%00.html",
            "/%00/../outside.txt",
            "/%0d%0a",
            "/%ff%fe",
            "/C:",
            "/C:outside.txt",
            "/C:\\Windows\\win.ini",
            "//server/share/outside.txt",
            "/\\\\server\\share\\outside.txt",
            "/CON",
            "/NUL",
        ],
    )
    def test_odd_characters_are_handled(
        self, spa_app: FastAPI, raw_target: str
    ) -> None:
        """NUL bytes, drive letters, UNC paths and device names never cause a server error."""
        status, body = raw_request(spa_app, raw_target)
        assert OUTSIDE_MARKER not in body
        assert status in (200, 404)

    def test_symlink_pointing_outside_is_not_served(
        self, spa_app: FastAPI, dist_dir: Path, workspace: Path
    ) -> None:
        """A link inside the build folder that points outside is not followed."""
        link = dist_dir / "link.txt"
        try:
            os.symlink(workspace / "outside.txt", link)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks are not available on this system")
        assert_no_outside_content(*raw_request(spa_app, "/link.txt"))

    def test_directory_link_pointing_outside_is_not_served(
        self, spa_app: FastAPI, dist_dir: Path, workspace: Path
    ) -> None:
        """A directory link that points outside is not followed."""
        link = dist_dir / "linked-dir"
        try:
            os.symlink(workspace / "dist-sibling", link, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks are not available on this system")
        assert_no_outside_content(*raw_request(spa_app, "/linked-dir/outside.txt"))

    def test_directories_are_not_served(self, spa_app: FastAPI) -> None:
        """Requests for a folder return index.html and never an error."""
        for raw_target in ("/subdir", "/subdir/", "/assets", "/assets/"):
            status, body = raw_request(spa_app, raw_target)
            assert status in (200, 307, 404)
            assert "index page" in body or status in (307, 404)

    def test_errors_do_not_expose_file_system_paths(
        self, spa_app: FastAPI, workspace: Path
    ) -> None:
        """Response bodies never contain the temporary folder's real path."""
        for raw_target in ("/%00", "/..%00/x", "/../outside.txt", "/subdir"):
            _, body = raw_request(spa_app, raw_target)
            assert str(workspace) not in body


class TestNormalServing:
    """Normal frontend behaviour must keep working."""

    def test_root_returns_index(self, spa_client: TestClient) -> None:
        """The root path returns index.html."""
        response = spa_client.get("/")
        assert response.status_code == 200
        assert response.text == INDEX_HTML

    def test_real_file_is_served(self, spa_client: TestClient) -> None:
        """A real file in the build folder is served with its contents."""
        response = spa_client.get("/favicon.svg")
        assert response.status_code == 200
        assert response.text == "<svg></svg>"

    def test_nested_file_is_served(self, spa_client: TestClient) -> None:
        """A file in a subfolder is served with its contents."""
        response = spa_client.get("/subdir/nested.txt")
        assert response.status_code == 200
        assert response.text == NESTED_TXT

    def test_asset_is_served(self, spa_client: TestClient) -> None:
        """Files under /assets are served by the static mount."""
        response = spa_client.get("/assets/app.js")
        assert response.status_code == 200
        assert response.text == ASSET_JS

    def test_unknown_route_returns_index(self, spa_client: TestClient) -> None:
        """Unknown client-side routes return index.html."""
        for path in ("/dashboard/settings", "/transcripts/123", "/missing.txt"):
            response = spa_client.get(path)
            assert response.status_code == 200
            assert response.text == INDEX_HTML

    def test_dotted_names_inside_build_folder_are_served(
        self, spa_client: TestClient, dist_dir: Path
    ) -> None:
        """Dots that stay inside the build folder are allowed."""
        (dist_dir / "a.b.txt").write_text("dotted")
        assert spa_client.get("/a.b.txt").text == "dotted"
        assert spa_client.get("/subdir/../a.b.txt").text == "dotted"


class TestExistingRoutesUnchanged:
    """Non-frontend routes behave the same as before."""

    def test_health(self, spa_client: TestClient) -> None:
        """/health is answered by the health route."""
        response = spa_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_health_prefixed_path_is_not_intercepted(
        self, spa_client: TestClient
    ) -> None:
        """Paths starting with 'health' are left alone by the frontend route."""
        response = spa_client.get("/health/extra")
        assert response.status_code == 200
        assert response.text == "null"

    def test_docs(self, spa_client: TestClient) -> None:
        """/docs still serves the API documentation page."""
        response = spa_client.get("/docs")
        assert response.status_code == 200
        assert "swagger-ui" in response.text

    def test_openapi_json(self, spa_client: TestClient) -> None:
        """/openapi.json still serves the schema."""
        response = spa_client.get("/openapi.json")
        assert response.status_code == 200
        assert "openapi" in response.json()

    def test_redoc(self, spa_client: TestClient) -> None:
        """/redoc still serves the documentation page."""
        response = spa_client.get("/redoc")
        assert response.status_code == 200
        assert "redoc" in response.text.lower()

    def test_unknown_api_path_is_left_alone(self, spa_client: TestClient) -> None:
        """Unknown /api/ paths keep their current response and never return index.html."""
        response = spa_client.get("/api/does-not-exist")
        assert response.status_code == 200
        assert response.text == "null"
        assert INDEX_HTML not in response.text
