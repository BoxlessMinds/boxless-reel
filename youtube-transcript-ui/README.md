# Boxless Reel - Web Interface

A modern React frontend for extracting, viewing, and querying YouTube transcripts with AI-powered Q&A.

## Features

- Extract transcripts from YouTube URLs
- Browse and search transcripts with pagination
- View transcripts with timestamped segments
- Chat with transcripts using AI-powered Q&A
- Manage conversation sessions

## Tech Stack

| Category | Technology |
|----------|------------|
| Framework | React 18 |
| Language | TypeScript |
| Build Tool | Vite |
| Data Fetching | TanStack React Query |
| Routing | React Router DOM |
| Styling | Tailwind CSS |
| UI Components | shadcn/ui (Radix UI) |
| Forms | React Hook Form + Zod |

## Prerequisites

- Node.js 24+ and npm
- The API running (see the [main README](../README.md))

## Development Setup

```bash
# Install dependencies
npm install

# Start development server (http://localhost:8080; /api goes to the API on port 8001)
npm run dev
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | empty (same origin) | Optional. Leave it unset: the app calls `/api` on its own address, which the dev server forwards to the API on port 8001 and nginx forwards in Docker. Set it only when the UI is served from a different address than the API. |

## Available Scripts

```bash
# Start development server
npm run dev

# Production build
npm run build

# Development build with source maps
npm run build:dev

# Preview production build
npm run preview

# Lint code
npm run lint

# Type-check without building
npm run typecheck
```

## Project Structure

```
src/
├── api/                    # API client layer
│   ├── baseUrl.ts          # Where API calls go (same origin by default)
│   ├── client.ts           # Base HTTP client
│   ├── types.ts            # TypeScript interfaces
│   ├── transcripts.ts      # Transcript API endpoints
│   ├── sessions.ts         # Session/Chat API endpoints
│   └── ...                 # One file per API area
├── components/
│   ├── chat/               # Chat components
│   ├── layout/             # Layout components
│   ├── transcript/         # Transcript components
│   └── ui/                 # shadcn/ui components
├── contexts/               # React context providers
├── hooks/                  # Custom React hooks
├── pages/                  # Page components
├── lib/                    # Utility functions
├── types/                  # Shared TypeScript types
└── utils/                  # Formatters and helpers
```

## Docker

The frontend can be run in Docker using the project's docker-compose:

```bash
# From project root
docker compose up frontend
```

This serves the production build via Nginx on port 8050.

## Related Documentation

- [Main README](../README.md) - Full setup guide and settings
- [Contributing](../CONTRIBUTING.md) - How to propose changes
- API reference - open `/docs` on your running API, for example <http://localhost:5050/docs> with Docker
