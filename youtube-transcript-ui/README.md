# Boxless Transcripts - Frontend

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

- Node.js 18+
- npm or yarn
- Backend API running (see main project README)

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
```

## Project Structure

```
src/
├── api/                    # API client layer
│   ├── client.ts           # Base HTTP client
│   ├── types.ts            # TypeScript interfaces
│   ├── transcripts.ts      # Transcript API endpoints
│   └── sessions.ts         # Session/Chat API endpoints
├── components/
│   ├── chat/               # Chat components
│   ├── layout/             # Layout components
│   ├── transcript/         # Transcript components
│   └── ui/                 # shadcn/ui components
├── hooks/                  # Custom React hooks
├── pages/                  # Page components
├── lib/                    # Utility functions
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

- [UI Architecture](../DOCUMENTATION/UI_Architecture.md) - Detailed architecture documentation
- [API Reference](../DOCUMENTATION/API_Reference.md) - Backend API endpoints
- [Getting Started](../DOCUMENTATION/Getting_Started.md) - Full project setup guide
