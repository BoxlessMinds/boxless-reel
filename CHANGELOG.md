# Changelog

All notable changes to this project are recorded in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - Unreleased

The first public release of Boxless Reel. The app was built privately from January to September 2026, across 41 pull requests, before being published as open source with a fresh history.

### Added

- **Transcripts:** extract transcripts from YouTube URLs (watch, `youtu.be`, `shorts/`, `embed/` and `live/` formats) with title, channel, thumbnail, duration and timestamped segments. An optional Whisper fallback handles videos without captions.
- **AI chat:** ask questions about a transcript and get answers with timestamp citations. Supports Claude or GPT, multi-turn sessions, chat across several transcripts, uploaded documents (PDF, DOCX, TXT, MD), optional web search, and saved chat artifacts.
- **Accounts:** multi-user login with admin and user roles, invitation-based registration, and per-user API keys encrypted at rest.
- **Playlist manager:** connect your own YouTube account to sync, dedupe, clean up, copy, build and reorder playlists. Every change is planned and reviewed before it's applied, within a daily quota budget.
- A React web UI, a Docker Compose setup, and a Postman collection for the API.
