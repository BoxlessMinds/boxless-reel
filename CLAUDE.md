# CLAUDE.md - Project Guide for Claude Code

## Project Overview

This is a RESTful API built with Python FastAPI that extracts, stores, and manages transcripts from YouTube videos. The API enables transcript extraction for analysis and document generation workflows.

## Tech Stack

- **Framework:** FastAPI
- **Database:** SQLite with SQLAlchemy ORM
- **Package Manager:** uv (not pip)
- **Python Version:** 3.11+
- **Transcript Extraction:** youtube-transcript-api
- **Metadata Extraction:** yt-dlp

## Quick Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn src.main:app --reload

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src

# Add a new dependency
uv add <package-name>

# Add a dev dependency
uv add --dev <package-name>
```

## Project Structure

```
youtube-transcript-api/
├── src/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Environment configuration
│   ├── database.py             # SQLAlchemy setup and session
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic request/response schemas
│   ├── repositories/           # Data access layer (database operations)
│   ├── services/               # Business logic layer
│   └── routers/                # API route handlers
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   └── test_*.py               # Test files
├── pyproject.toml
└── .env                        # Environment variables (not committed)
```

## Architecture Patterns

### Layered Architecture
1. **Routers** → Handle HTTP requests, validate input, return responses
2. **Services** → Business logic, orchestration, no direct DB access
3. **Repositories** → Database operations, queries, CRUD
4. **Models** → SQLAlchemy ORM definitions
5. **Schemas** → Pydantic validation models

### Dependency Injection
Use FastAPI's `Depends()` for injecting:
- Database sessions (`get_db`)
- Repository instances
- Service instances

Example:
```python
@router.post("/extract")
async def extract_transcript(
    request: TranscriptExtractRequest,
    service: TranscriptService = Depends(get_transcript_service)
):
    ...
```

## Code Conventions

### Type Hints
Always use type hints for function parameters and return values:
```python
def get_by_id(self, transcript_id: UUID) -> Optional[Transcript]:
    ...
```

### Docstrings
Use docstrings for all public functions and classes:
```python
def extract_video_id(url: str) -> str:
    """
    Extract the video ID from a YouTube URL.
    
    Args:
        url: YouTube URL in any common format
        
    Returns:
        The 11-character video ID
        
    Raises:
        ValueError: If the URL format is not recognized
    """
```

### Error Handling
- Use HTTPException for API errors with appropriate status codes
- Create custom exception classes for business logic errors
- Always log exceptions before re-raising

### Naming Conventions
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/transcripts/extract` | Extract transcript from YouTube URL |
| GET | `/api/transcripts` | List transcripts with filtering |
| GET | `/api/transcripts/{id}` | Get single transcript |
| DELETE | `/api/transcripts/{id}` | Delete transcript |

### HTTP Status Codes
- `200` - Success (GET, DELETE)
- `201` - Created (POST)
- `204` - No Content (DELETE alternative)
- `400` - Invalid YouTube URL format
- `404` - Transcript/video not found
- `409` - Transcript already exists for video
- `422` - Validation error
- `500` - Internal server error

## Database

### Schema: transcripts
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| video_id | String | Unique, YouTube video ID |
| title | String | Video title |
| channel_name | String | Nullable |
| thumbnail_url | String | Nullable |
| transcript_text | Text | Full transcript |
| transcript_segments | JSON | Timestamped segments |
| language | String | Language code |
| duration_seconds | Integer | Nullable |
| created_at | DateTime | Auto-set |
| updated_at | DateTime | Auto-updated |

### Session Management
Always use the session dependency and let FastAPI handle cleanup:
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Docker Database Backup
**Before making any changes that affect the database schema or data** (model changes, migrations, destructive operations), always back up the SQLite database from the running Docker container:

```bash
# 1. Find the running container
docker ps --filter "ancestor=transcript-api" --format "{{.Names}}"

# 2. Ensure the BACKUP folder exists
mkdir -p BACKUP

# 3. Copy the database file out of the container into BACKUP with a unique timestamped name
docker cp <container_name>:/app/transcripts.db ./BACKUP/transcripts_backup_$(date +%Y%m%d_%H%M%S).db

# 4. Verify the backup is valid
sqlite3 ./BACKUP/transcripts_backup_*.db "PRAGMA integrity_check;"
```

This applies whenever you:
- Modify SQLAlchemy models in `models/`
- Delete or recreate `transcripts.db`
- Run any operation that alters tables (add/drop columns, rename, etc.)
- Perform bulk deletes or updates

Do **not** proceed with schema changes until the backup is confirmed successful.

## Testing

### Test Database
Tests use an in-memory SQLite database configured in `conftest.py`.

### Test Structure
```python
class TestTranscriptExtraction:
    def test_extract_valid_url(self, client, mock_youtube_service):
        ...
    
    def test_extract_invalid_url_returns_400(self, client):
        ...
    
    def test_extract_duplicate_returns_409(self, client, existing_transcript):
        ...
```

### Mocking External Services
Mock `youtube-transcript-api` and `yt-dlp` calls in tests to avoid hitting external services.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | `sqlite:///./transcripts.db` | Database connection string |
| LOG_LEVEL | `INFO` | Logging level |

## Common Tasks

### Adding a New Endpoint
1. Add Pydantic schema in `schemas/`
2. Add repository method if new DB operation needed
3. Add service method for business logic
4. Add route handler in `routers/`
5. Write tests

### Modifying the Database Schema
1. Update SQLAlchemy model in `models/`
2. Update Pydantic schemas in `schemas/`
3. Delete `transcripts.db` to recreate (or use migrations for production)
4. Update tests

### YouTube URL Formats to Support
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/watch?v=VIDEO_ID&t=123`
- `https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID`

## Troubleshooting

### "No transcript available"
Some videos don't have transcripts. The API should return 404 with a clear message.

### "Video unavailable"
Private, deleted, or region-locked videos. Return 404.

### Rate Limiting
YouTube may rate-limit requests. Consider adding delays between bulk extractions.

## Do Not

- Do not use `pip` directly; use `uv` for all package management
- Do not commit `.env` files
- Do not store API keys in code
- Do not make synchronous blocking calls in async endpoints
- Do not skip type hints
- Do not catch and silence exceptions without logging
