# Boxless Transcripts

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![React 18](https://img.shields.io/badge/React-18.3+-61DAFB.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5.8+-3178C6.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)

A full-stack application for extracting, storing, and intelligently querying YouTube video transcripts. Features a modern React frontend and a FastAPI backend with AI-powered natural language querying through LLM agents.

## Overview

Boxless Transcripts makes it easy to:
- **Extract** transcripts from any YouTube video with a single click
- **Browse** your transcript library with search and filtering
- **Chat** with transcripts using AI - ask questions and get answers with timestamp citations
- **Manage** conversation sessions for multi-turn Q&A

## Screenshots

| Home | Transcript View | Chat |
|------|-----------------|------|
| Extract transcripts | View with timestamps | AI-powered Q&A |

## Quick Start with Docker

The fastest way to get started is with Docker Compose:

```bash
# Clone the repository
git clone https://github.com/yourusername/boxless-transcripts.git
cd boxless-transcripts

# Configure environment (add your API keys and a login secret)
cp .env.example .env.docker
# Edit .env.docker with your OPENAI_API_KEY and/or ANTHROPIC_API_KEY
# Also set JWT_SECRET_KEY (required, at least 32 characters). Generate one with:
#   openssl rand -hex 32

# Start the application
docker compose up -d
```

Access the application:
- **Frontend**: http://localhost:8050
- **API**: http://localhost:5050
- **API Docs**: http://localhost:5050/docs

## Features

### Core Transcript Management
- Extract transcripts from YouTube videos (supports multiple URL formats)
- Store transcripts with full metadata (title, channel, thumbnail, duration)
- List, search, and filter transcripts by title or language
- View transcripts with clickable timestamp segments

### AI-Powered Chat
- Natural language querying of transcript content
- Session-based multi-turn conversations
- Timestamp citations linking directly to video moments
- Support for **Anthropic Claude** and **OpenAI GPT** models
- Vector-based semantic search with LanceDB
- **Web Search Integration** (Tavily) for supplementary context and fact verification
- **Document Upload** - Add PDF, DOCX, TXT, or MD files as additional context (up to 5 per session)

### Modern UI
- Clean, responsive design with dark mode support
- Real-time transcript extraction with progress feedback
- Tabbed interface for transcript viewing and chat
- Session management for organizing conversations

### Playlist Management
- Connect your own Google account (OAuth) to sync your YouTube playlists into a local, searchable cache
- Dedupe playlists and purge unavailable (deleted/private) items
- Purge already-watched videos by importing a Google Takeout `watch-history.json` export
- Copy or build playlists from other playlists, or add videos directly by pasting URLs
- Bulk move items between playlists and reorder playlist contents
- Every change goes through a **plan → review → apply** workflow: generate a dry-run plan, review exactly what will change and its quota cost, then apply it against a shared, app-wide daily YouTube Data API budget (not a per-user one) - so a multi-day plan can safely be resumed the next day without duplicating or losing items

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, Pydantic |
| **AI/ML** | Anthropic Claude, OpenAI GPT, LanceDB (vector search), Tavily (web search) |
| **Data** | SQLite (transcripts), LanceDB (embeddings) |
| **Infrastructure** | Docker, Nginx |

## Manual Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) package manager
- (Optional, for playlist management) A Google Cloud Console OAuth client:
  1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/) and enable the **YouTube Data API v3**.
  2. Create an **OAuth 2.0 Client ID** (Web application type).
  3. Add an authorized redirect URI matching `GOOGLE_OAUTH_REDIRECT_URI` (default `http://localhost:8001/api/youtube-auth/callback`).
  4. Set `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in your `.env` from the credentials generated above.

### Backend Setup

```bash
# Install Python dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your settings. JWT_SECRET_KEY is required (at least 32 characters).
# Generate one with: uv run python -c "import secrets; print(secrets.token_hex(32))"

# Run the API server
uv run uvicorn src.main:app --reload
```

API available at http://localhost:8000

### Frontend Setup

```bash
# Navigate to frontend directory
cd youtube-transcript-ui

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend available at http://localhost:8080

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./transcripts.db` | Database connection string |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ANTHROPIC_API_KEY` | - | API key for Claude models |
| `OPENAI_API_KEY` | - | API key for OpenAI models (required for embeddings) |
| `DEFAULT_LLM_PROVIDER` | `anthropic` | Default LLM provider (`anthropic` or `openai`) |
| `DEFAULT_MODEL` | `claude-sonnet-4-5` | Default model ID |
| `LANCEDB_URI` | `./data/lancedb` | Vector database storage path |
| `TAVILY_API_KEY` | - | API key for web search (optional) |
| `WEB_SEARCH_ENABLED` | `true` | Enable/disable web search |
| `WEB_SEARCH_MAX_RESULTS` | `5` | Maximum web search results (1-10) |
| `REQUIRE_INVITATION_CODE` | `true` | Require invitation to register (`true`/`false`, can be overridden by admin UI) |
| `DOCUMENTS_STORAGE_PATH` | `./data/documents` | Document storage directory |
| `MAX_DOCUMENTS_PER_SESSION` | `5` | Maximum documents per session |
| `JWT_SECRET_KEY` | - | **Required.** Secret for signing login tokens, at least 32 characters. The API will not start without it. Generate one with `openssl rand -hex 32` |
| `ALLOWED_ORIGINS` | `["http://localhost:3000","http://localhost:8080"]` | Allowed CORS origins (JSON list). Add your frontend URL for Docker/production. |
| `SETTINGS_ENCRYPTION_KEY` | *(auto-generated)* | Fernet key for encrypting API keys in database. Auto-generated if unset (won't persist across restarts). |
| `GOOGLE_OAUTH_CLIENT_ID` | - | Shared app-wide Google OAuth client ID (required for playlist management) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | - | Shared app-wide Google OAuth client secret (required for playlist management) |
| `GOOGLE_OAUTH_REDIRECT_URI` | `http://localhost:8001/api/youtube-auth/callback` | Must match a redirect URI registered in Google Cloud Console |
| `YOUTUBE_DAILY_QUOTA_LIMIT` | `10000` | YouTube Data API v3 daily unit quota for the app's shared OAuth client |
| `YOUTUBE_DEFAULT_APPLY_BUDGET` | `200` | Default units spent per apply() call when the caller doesn't specify a budget |
| `WATCH_HISTORY_STORAGE_PATH` | `./data/watch-history` | Path to store uploaded Google Takeout `watch-history.json` files |

### Docker Ports

| Service | Internal | External |
|---------|----------|----------|
| API | 8000 | 5050 |
| Frontend | 80 | 8050 |

## API Endpoints

### Transcript Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/transcripts/extract` | Extract transcript from YouTube URL |
| `GET` | `/api/transcripts` | List transcripts with filtering |
| `GET` | `/api/transcripts/{id}` | Get single transcript |
| `DELETE` | `/api/transcripts/{id}` | Delete transcript |

### Agent Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/transcripts/{id}/query` | One-shot query (no session) |
| `POST` | `/api/transcripts/{id}/sessions` | Create conversation session |
| `POST` | `/api/sessions/{id}/query` | Query within session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/{id}` | Get session with message history |
| `DELETE` | `/api/sessions/{id}` | Delete session |

### Auth Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/login` | Login with email/password |
| `POST` | `/api/auth/register` | Register (with or without invitation token) |
| `GET` | `/api/auth/registration-mode` | Get current registration mode |
| `POST` | `/api/auth/refresh` | Refresh access token |
| `POST` | `/api/auth/logout` | Logout (revoke refresh token) |
| `GET` | `/api/auth/me` | Get current user profile |
| `PUT` | `/api/auth/me` | Update profile or change password |

### Invitation Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/invitations` | Create invitation |
| `GET` | `/api/invitations` | List sent invitations |
| `DELETE` | `/api/invitations/{id}` | Revoke invitation |
| `POST` | `/api/invitations/validate` | Validate invitation token |

### Settings Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/settings` | Get LLM settings |
| `PUT` | `/api/settings` | Update LLM settings |
| `POST` | `/api/settings/validate-key` | Validate an API key |

### Admin Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/admin/users` | List all users |
| `PUT` | `/api/admin/users/{id}` | Update user role/status |
| `GET` | `/api/admin/settings/registration-mode` | Get registration mode |
| `PUT` | `/api/admin/settings/registration-mode` | Toggle registration mode |
| `POST` | `/api/admin/invitations/bulk` | Send bulk invitations |

### Document Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions/{id}/documents` | Upload document to session |
| `GET` | `/api/sessions/{id}/documents` | List session documents |
| `DELETE` | `/api/sessions/{id}/documents/{doc_id}` | Delete document |
| `GET` | `/api/documents` | List all user documents |
| `GET` | `/api/documents/{id}` | Get document details |

### Cross-Chat Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/cross-chat` | Create cross-chat session |
| `GET` | `/api/cross-chat` | List cross-chat sessions |
| `GET` | `/api/cross-chat/{id}` | Get cross-chat session details |
| `POST` | `/api/cross-chat/{id}/query` | Query across multiple transcripts |
| `DELETE` | `/api/cross-chat/{id}` | Delete cross-chat session |

### YouTube Auth Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/youtube-auth/connect` | Start Google OAuth consent flow |
| `GET` | `/api/youtube-auth/callback` | OAuth redirect callback |
| `GET` | `/api/youtube-auth/status` | Check current user's connection status |
| `DELETE` | `/api/youtube-auth/disconnect` | Revoke and remove stored Google credentials |

### Playlist Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/playlists/sync` | Sync the user's YouTube playlists into the local cache |
| `GET` | `/api/playlists` | List cached playlists |
| `GET` | `/api/playlists/{playlist_id}/items` | List a playlist's cached items |
| `GET` | `/api/playlists/quota` | Get current shared daily quota usage |

### Plan Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/plans` | Generate a dry-run plan (create, dedupe, purge_unavailable, copy, add_url, purge_watched, or move) |
| `GET` | `/api/plans/{plan_id}` | Get a plan's status and operations |
| `POST` | `/api/plans/{plan_id}/apply` | Apply (execute) a previously generated plan against YouTube, budget-limited |

### Watch History Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/watch-history/import` | Import a Google Takeout `watch-history.json` export |
| `GET` | `/api/watch-history` | List previously imported watch-history batches |

## Project Structure

```
boxless-transcripts/
├── src/                        # Python backend
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Environment configuration
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic request/response schemas
│   ├── repositories/           # Data access layer
│   ├── services/               # Business logic
│   ├── routers/                # API route handlers
│   └── agents/                 # LLM agent components
├── youtube-transcript-ui/      # React frontend
│   ├── src/
│   │   ├── api/                # API client layer
│   │   ├── components/         # React components
│   │   ├── hooks/              # Custom hooks
│   │   └── pages/              # Page components
│   ├── Dockerfile              # Frontend container
│   └── nginx.conf              # Nginx configuration
├── DOCUMENTATION/              # Detailed documentation
├── docker-compose.yml          # Docker orchestration
├── Dockerfile                  # API container
└── pyproject.toml              # Python project configuration
```

## Documentation

- **[Getting Started Guide](DOCUMENTATION/Getting_Started.md)** - Detailed setup and usage
- **[API Reference](DOCUMENTATION/API_Reference.md)** - Complete endpoint documentation
- **[API Architecture](DOCUMENTATION/API_Architecture/)** - Backend architecture details
- **[UI Architecture](DOCUMENTATION/UI_Architecture.md)** - Frontend architecture details

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src

# Run only unit tests (skip integration)
uv run pytest -m "not integration"
```

### Supported YouTube URL Formats

- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/watch?v=VIDEO_ID&t=123`
- Raw 11-character video ID

## License

Boxless Reel is released under the [MIT License](LICENSE).
