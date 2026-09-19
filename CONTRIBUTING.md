# Contributing to Boxless Reel

Thanks for your interest in improving Boxless Reel! Bug reports, documentation fixes and code contributions are all welcome.

Boxless Reel is maintained by one person in their spare time. I aim to reply to issues and pull requests within about a week. Please be patient if it takes a little longer.

By taking part, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- **Found a bug?** Search the existing issues first. If it's new, open an issue with the steps to reproduce it, what you expected, and what happened instead.
- **Want a new feature?** Open an issue to discuss it before you write any code. That way we can agree the approach first, and you won't spend time on something that doesn't fit.
- **Found a security problem?** Don't open an issue. Follow [SECURITY.md](SECURITY.md) instead.
- **New here?** Look for issues labelled `good first issue`.

### What's in scope

Boxless Reel is a **self-hosted** tool. These are out of scope:

- a hosted or multi-tenant service
- proxy, IP-rotation or other features designed to get around YouTube's limits
- anything that conflicts with YouTube's Terms of Service

If YouTube changes something and transcripts stop working, the cause is usually upstream in [`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api). Please check there first.

## Development setup

You'll need:

- Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/). This project uses uv for everything; please don't use `pip` directly.
- Node.js 20 for the web UI.
- ffmpeg, but only if you work on the Whisper transcription fallback.

To install everything and run the tests:

```bash
# Backend dependencies, including the test tools
uv sync --extra dev

# Run the test suite (skips tests that call paid APIs)
uv run pytest -m "not integration"

# Web UI
cd youtube-transcript-ui
npm install
npm run lint
npm run build
```

See the README for how to configure and run the app locally.

The unit tests mock YouTube and the LLM providers, so you don't need API keys to run them. Tests marked `integration` call real, paid APIs; only run them on purpose, with your own keys.

## Code conventions

The backend uses a layered architecture. Please keep to it:

| Layer | Folder | Responsibility |
|---|---|---|
| Routers | `src/routers/` | HTTP handling, input validation, responses |
| Services | `src/services/` | Business logic and orchestration; no direct database access |
| Repositories | `src/repositories/` | Database queries and CRUD |
| Models | `src/models/` | SQLAlchemy ORM definitions |
| Schemas | `src/schemas/` | Pydantic request and response models |

- Inject dependencies such as database sessions, repositories and services with FastAPI's `Depends()`.
- Add type hints to every function parameter and return value.
- Write docstrings for public functions and classes.
- Use `HTTPException` with the right status code for API errors, and custom exception classes for business-logic errors.
- Log exceptions before re-raising them. Never catch and silence an exception without logging it.
- Don't make blocking calls inside `async` endpoints.
- Naming: `snake_case` for files, functions and variables; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants.

### Adding an endpoint

1. Add the Pydantic schema in `src/schemas/`.
2. Add a repository method if it needs a new database operation.
3. Add the service method with the business logic.
4. Add the route handler in `src/routers/`, and register any new router.
5. Write tests.

### Tests

- Add or update tests for every change.
- Mock YouTube (`youtube-transcript-api`, `yt-dlp`, the YouTube Data API) and the LLM providers, so tests never make network calls.
- Tests use an in-memory SQLite database, which is set up in `tests/conftest.py`.

## Submitting a pull request

1. Fork the repository and create a branch from `main`.
2. Keep each pull request focused on one change.
3. Make sure the tests pass, the UI lint passes, and the UI builds.
4. Update the README or other docs if behaviour or configuration changes.
5. Add an entry under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for anything a user would notice.
6. Open the pull request, explaining what changed and why. Link the related issue.

**Never commit secrets**: no API keys, passwords, tokens or `.env` files. Use `.env.example` to document any new setting.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE) that covers this project.
