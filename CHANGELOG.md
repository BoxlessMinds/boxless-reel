# Changelog

All notable changes to this project are recorded in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Web interface:** it now calls the API on its own address (nginx forwards `/api` in Docker, and the dev server forwards it to port 8001 in development), so the Docker quick start works without any `ALLOWED_ORIGINS` setting, and the Docker image no longer has an API address built in. `VITE_API_URL` is now optional; set it only if you serve the web interface from a different address than the API. If you already run the app with Docker, run `docker compose up -d --build` to pick this up.
- **Docker:** the database now lives in the `data` folder (`data/transcripts.db`), so a fresh clone starts without any setup. If you already run the app with Docker, do this once: run `docker compose down` (without `-v`), move `transcripts.db` into the `data` folder, then run `docker compose up -d --build`. If an earlier failed start left a folder named `transcripts.db`, you can delete it.
- **Docker:** the Docker Compose project is now named `boxless-reel`, and the containers are no longer given fixed names, so two copies of the app can run side by side (for example, to test an upgrade). If you already run the app with Docker, do this once: run `docker compose -p boxless-transcript-api down` (without `-v`), then `docker compose up -d --build`. Your data stays in `transcripts.db` and `data/`.

## [0.1.0] - Unreleased

The first public release of Boxless Reel. The app was built privately from January to September 2026, across 41 pull requests, before being published as open source with a fresh history.

### Added

- **Transcripts:** extract transcripts from YouTube URLs (watch, `youtu.be`, `shorts/`, `embed/` and `live/` formats) with title, channel, thumbnail, duration and timestamped segments. An optional Whisper fallback handles videos without captions.
- **AI chat:** ask questions about a transcript and get answers with timestamp citations. Supports Claude or GPT, multi-turn sessions, chat across several transcripts, uploaded documents (PDF, DOCX, TXT, MD), optional web search, and saved chat artifacts.
- **Accounts:** multi-user login with admin and user roles, invitation-based registration, and per-user API keys encrypted at rest.
- **Playlist manager:** connect your own YouTube account to sync, dedupe, clean up, copy, build and reorder playlists. Every change is planned and reviewed before it's applied, within a daily quota budget.
- A React web UI, a Docker Compose setup, and a Postman collection for the API.
