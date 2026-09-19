# Postman collection

A ready-made collection for exercising every endpoint of the API by hand, in
Postman's Collection Runner, or with Newman.

| File | What it is |
|------|------------|
| `transcript-api.postman_collection.json` | Postman Collection v2.1: 68 requests in 13 folders, covering all 56 API routes |
| `transcript-api.postman_environment.json` | `base_url`, login credentials, tokens, chaining ids, and the `allow_live` switch |
| `fixtures/watch-history.sample.json` | Sample Google Takeout export for Watch History → Import |
| `fixtures/sample-notes.md` | Sample file for Documents → Upload Session Document |

## Quick start (Postman app)

1. Start the API on port 8001: `uv run uvicorn src.main:app --reload --port 8001`
2. In Postman: **Import** → select both JSON files.
3. Pick the **transcript-api (local)** environment and set `email` and `password` to a
   local account. The Admin folder needs an admin account; see
   [Seeding a first account](#seeding-a-first-account-on-a-fresh-database).
4. Send **Auth → Login**. `access_token` and `refresh_token` fill in automatically
   (check the environment quick look, the eye icon).
5. Send anything else. Each folder's description lists what it needs first.

The two upload requests point at `postman/fixtures/...`, a path relative to the repo
root. Set **Settings → General → Working directory** to the repo root, or re-pick
the file in the request's Body tab.

## `base_url` defaults to port 8001, not 8000

This is deliberate. The frontend (`VITE_API_URL` in `youtube-transcript-ui/.env`) and the
Google OAuth redirect URI default (`src/config.py`) both expect the API on **8001**.
`CLAUDE.md`, the top-level `README.md` and `DOCUMENTATION/API_Reference.md` still say 8000;
those are out of date. Start the dev server with `--port 8001`, or change `base_url`.
If `localhost` won't connect on your machine, use `http://127.0.0.1:8001`
(uvicorn binds IPv4 only by default). A trailing slash on `base_url` is harmless: the
collection strips it before every request. Anything after the port (such as `/api`)
still breaks every URL.

## Where the tokens come from

- **Login** has a test script that copies `access_token` and `refresh_token` from the
  response into the active environment. You don't copy anything by hand.
- The collection uses **Bearer `{{access_token}}`** auth, and every request inherits it
  except the public ones, which are set to *No Auth*: Health Check, Get Registration
  Mode, Login, Refresh Tokens, Register, Logout, Validate Invitation Token, and
  OAuth Callback.
- Access tokens expire after **15 minutes** by default. When requests start returning
  401, send **Refresh Tokens** or Login again. Refresh rotates *both* tokens, and its
  test script stores both.
- **Logout** revokes `refresh_token`. Changing the password through
  `PUT /api/auth/me` revokes every refresh token for the account. After either one,
  Login again.

## Seeding a first account on a fresh database

Nothing creates an admin automatically, and **Register** always creates a
`role: "user"` account. Create the first admin with the CLI:

```powershell
uv run python -m src.cli create-admin --email you@example.com         # prompts for the password
uv run python -c "from src.cli import create_admin; create_admin('you@example.com', 'your-password')"   # non-interactive
```

Both commands create the tables if they don't exist yet. Put those credentials in the
environment's `email` and `password`.

Registration is **invite-only** by default. The Auth folder handles this: it sends
*Invite a New User*, then *Register* with that invitation's token. To open
registration, use **Admin → Update Registration Mode**. `REQUIRE_INVITATION_CODE=false`
in `.env` does not work for a local uvicorn: the flag is read from the process
environment, and `.env` values never reach it. Set it in the shell before starting the
server instead. A value saved through the admin endpoint overrides both.

## Live requests are skipped unless you opt in

Requests whose names start with **`[LIVE]`** call YouTube/Google or a paid API. Each
one has a pre-request guard that skips it unless the environment variable
**`allow_live`** is `"true"`. The default is `"false"`, so Collection Runner and Newman
runs are safe unless you opt in. Set it to `true` only for the requests you mean to
send, and set it back afterwards.

| Request | What it calls |
|---------|---------------|
| Transcripts → Extract Transcript | YouTube captions / yt-dlp, the OpenAI Whisper fallback, OpenAI embeddings |
| Agent → Create Session, Create Second Session | OpenAI embeddings (indexing the transcript) |
| Agent → One-Shot Query, Query Session | Anthropic/OpenAI LLM, Tavily web search |
| Documents → Upload Session Document | OpenAI embeddings |
| Settings → Validate API Key | the provider's API |
| Cross-Chat → Create Cross-Chat Session | OpenAI embeddings, LLM agent setup |
| Cross-Chat → Query Cross-Chat Session | LLM, Tavily web search |
| YouTube Auth → OAuth Callback | Google's token exchange |
| YouTube Auth → Disconnect | Google's token revoke endpoint |
| Playlists → Sync Playlists | YouTube Data API (**spends quota**) |
| Plans → Create Plan - add_url (playlist URL), Create Plan - copy | YouTube Data API, when the source playlist isn't cached |
| Plans → Create Plan - purge_unavailable (deleted_and_private) | YouTube `videos.list` enrichment |
| Plans → Apply Plan | **Edits real playlists** and spends quota |

- The server loads `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` from `.env` at startup, so
  LLM and embedding requests **cost real money even against a local server**.
- Before running Sync or Apply against a Google-connected instance, check
  **Playlists → Get Quota Status** (or run `/quota-budget-check` in Claude Code). The
  10,000-unit daily quota is shared by all users and resets at midnight Pacific. The
  default apply budget, 200 units, covers four writes.
- These plan kinds are generated locally, are never marked live, and never change
  YouTube (a plan is a dry run): `create`, `dedupe`, `purge_unavailable` (mode
  `deleted`, no enrich), `purge_watched`, `move`, `reorder`, and `add_url` with
  individual video URLs.

## Chaining and skipped requests

Ids pass from one request to the next through environment variables that test scripts
set. No request contains a hard-coded id.

| Variable | Set by | Used by |
|----------|--------|---------|
| `access_token`, `refresh_token` | Login, Refresh Tokens | every authenticated request; Refresh, Logout |
| `invitee_email` | Invite a New User, Create Invitation (pre-request: fresh address each run) | Register, Validate Invitation Token |
| `invitation_id`, `invitation_token` | Invite a New User, Create Invitation | Register, Validate, Revoke, Clear |
| `user_id` | Register | Admin → Update User, Delete User |
| `transcript_id`, `video_id` | Extract Transcript | Get/Delete Transcript, the Agent folder |
| `session_id`, `second_session_id` | Agent → Create Session, Create Second Session | Agent, Documents, Cross-Chat |
| `document_id` | Upload Session Document | Get Document, Delete Session Document |
| `cross_chat_session_id` | Create Cross-Chat Session | Query / Get / Delete Cross-Chat Session |
| `google_oauth_state` | Get Connect URL | OAuth Callback |
| `google_auth_code` | you, copied from Google's browser redirect | OAuth Callback |
| `playlist_id`, `target_playlist_id`, `youtube_playlist_id` | List Playlists (only when empty) | List Playlist Items, Plans |
| `watch_history_import_id` | Import Watch History | List Watch History Imports |
| `plan_id` | every Create Plan request | Get Plan, Apply Plan (**the last plan created**) |
| `display_name` | Get Current User | Update Current User (writes it back unchanged) |
| `require_invitation` | Get Registration Mode (admin) | Update Registration Mode (writes it back unchanged) |

- **Empty ids skip, they don't fail.** A collection-level pre-request script checks
  each request for chaining variables. If one is still empty, the script skips the
  request and logs why in the console, rather than sending a blank path segment. A
  blank segment is worse than a skip. When `youtube-transcript-ui/dist` is built,
  `src/main.py`'s SPA catch-all answers any unknown `GET /api/...` with **200 and a null
  body**, so `GET /api/sessions/` with no id would look like a success. As a second
  guard, every response is also asserted to be non-null JSON, and every request checks
  the response shape, not just the status code.
- Delete requests clear the ids they deleted, so the requests that need those ids
  skip afterwards.
- As a result, in a run where `allow_live` is `false`, requests that need an id from a
  live request are skipped too (for example, Get Transcript after Extract). They don't
  404. To run them against existing data, paste a real id into the variable.

## Folder order

Each folder runs top-to-bottom in the Collection Runner: create, then read, then
update, then delete. In Auth, Logout comes last.

Some folders need ids from another folder:

- **Agent** needs `transcript_id`.
- **Documents** and **Cross-Chat** need the session ids that Agent creates.
- **Plans** need playlist ids from Playlists. `purge_watched` finds matches only after
  a Watch History import.

Because each folder cleans up after itself, the live flow is:

1. Transcripts → Extract Transcript, on its own.
2. Agent → the two Create Session requests.
3. The Documents and Cross-Chat folders.
4. Agent's two Delete requests.
5. Transcripts → Delete Transcript.

## Running with Newman

The live guard makes a whole-collection run safe, so no `--folder` flags are needed:

```powershell
npx newman run postman\transcript-api.postman_collection.json `
  -e postman\transcript-api.postman_environment.json `
  --env-var "base_url=http://127.0.0.1:8011" `
  --env-var "email=newman-admin@example.com" `
  --env-var "password=Newman-Passw0rd!"
```

Run it from the **repo root** so the upload fixtures resolve (or pass `--working-dir`).
Don't commit `--export-environment` output: it contains live tokens.

**A run writes data.** It creates invitations (two of them via bulk), registers a
throwaway user and then deletes it, writes your per-user settings
(`max_context_chunks`, `web_search_*`), saves the registration mode unchanged, imports
the sample watch history, and creates dry-run plans. Run it against a
**throwaway database**. Never run it against your real `transcripts.db`, and never
against the Docker instance (`boxless-api`, port 5050). To set up a throwaway server,
run these from the repo root in one PowerShell session:

```powershell
$T = Join-Path $env:TEMP 'transcript-api-newman'; New-Item -ItemType Directory -Force $T | Out-Null
$env:DATABASE_URL = "sqlite:///$($T -replace '\\','/')/newman.db"
$env:LANCEDB_URI = "$T\lancedb"; $env:DOCUMENTS_STORAGE_PATH = "$T\documents"; $env:WATCH_HISTORY_STORAGE_PATH = "$T\watch-history"
$env:OPENAI_API_KEY = 'dummy-not-a-key'; $env:ANTHROPIC_API_KEY = 'dummy-not-a-key'   # a stray live request fails instead of spending
uv run python -c "from src.cli import create_admin; create_admin('newman-admin@example.com', 'Newman-Passw0rd!')"
uv run uvicorn src.main:app --port 8011
```

Then run the Newman command above from a second terminal.

## Known API issues (found while building this)

1. **Refresh Tokens, Register (with an invitation) and Validate Invitation Token return
   500 on SQLite.** `RefreshToken.is_expired` and `Invitation.is_valid` / `is_expired`
   compare `datetime.now(timezone.utc)` with an `expires_at` that SQLite returns without a
   timezone (`src/models/refresh_token.py:59`, `src/models/invitation.py:70,75`), which
   raises `TypeError`. **Until this is fixed, Newman reports 9 failed assertions, three
   in each of those requests.** The rest of the run is unaffected: Login's access
   token keeps working, and Admin → Update/Delete User skip because Register can't set
   `user_id`. With that comparison patched, the whole run passes.
2. When the frontend is built, unknown `GET /api/...` paths return 200 with a null body
   instead of 404 (`src/main.py:208-209`). This is why the assertions check body shape.
3. `REQUIRE_INVITATION_CODE` in `.env` doesn't reach a local uvicorn (see
   [Seeding a first account](#seeding-a-first-account-on-a-fresh-database)).

## Where this differs from the story's Scope

- `base_url` is `http://localhost:8001`, not `:8000` (see above).
- **Documents:** `/api/documents` is read-only (list and get). Upload, per-session list
  and delete live under `/api/sessions/{session_id}/documents`. The Documents folder
  still groups all five, as `API_Reference.md` does.
- **Refresh** rotates both tokens, so its test script captures both, not just the access
  token.
- **Register** needs an invitation token by default, so the Auth folder mints one first.
- The collection also covers routes that `API_Reference.md` omits: Cross-Chat,
  YouTube Auth, Playlists, Plans, Watch History, and the three registration-mode
  endpoints.
- **Fixtures:** two files under `postman/fixtures/`. The multipart requests need real
  files, and `tests/` has no Takeout file to reuse.
