# Security

Security requirements for the autonomous Telugu devotional YouTube production platform.

---

## Authentication and authorization

- Secure password hashing (Argon2id or bcrypt via a maintained library).
- JWT access tokens and/or secure HTTP-only session cookies for the admin dashboard.
- Role-based access where needed (`admin`, `operator`).
- Short-lived access tokens; refresh rotation if refresh tokens are used for app users.
- Lockouts / rate limits on login endpoints.

## Secrets management

- All secrets via environment variables or a secret store — **never** committed.
- Provide `.env.example` in Phase 1 with empty placeholders (this Phase 0 doc lists the inventory).
- Never expose API keys, OAuth client secrets, or n8n keys to the React frontend.
- Provider secrets referenced from `provider_configurations.secrets_ref` (env names), not stored as plaintext JSON values.

### Planned `.env.example` inventory (created in Phase 1)

| Variable | Purpose |
| --- | --- |
| `APP_SECRET_KEY` | Session/JWT signing |
| `TOKEN_ENCRYPTION_KEY` | Encrypt YouTube refresh tokens at rest |
| `DATABASE_URL` | PostgreSQL |
| `REDIS_URL` | Redis / Celery |
| `CORS_ORIGINS` | Allowed frontend origins |
| `CURSOR_API_KEY` | Cursor SDK — LLM only |
| `CURSOR_LLM_MODEL` | Default `composer-2.5` |
| `MUREKA_API_KEY` | Music via official Mureka API |
| `MUREKA_MODEL` | Default `auto` |
| `WAVESPEED_API_KEY` | Optional backup (ACE-Step) |
| `SUNOAPI_API_KEY` | Legacy |
| `AIMLAPI_API_KEY` | Legacy |
| `GEMINI_API_KEY` | Gemini video API |
| `GEMINI_VIDEO_MODEL` | Default `gemini-omni-1.1-flash` |
| `GEMINI_VIDEO_DURATION` | Default `10` |
| `GEMINI_VIDEO_RESOLUTION` | Default `360p` (cheap) |
| `GOOGLE_CLIENT_ID` | YouTube OAuth |
| `GOOGLE_CLIENT_SECRET` | YouTube OAuth |
| `GOOGLE_OAUTH_REDIRECT_URI` | Callback URL |
| `GOOGLE_PROJECT_ID` | Google Cloud project id |
| `N8N_WEBHOOK_SECRET` | FastAPI ↔ n8n auth |
| `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` | n8n UI protection |
| `MEDIA_ROOT` | `/app/storage` |
| `MAX_UPLOAD_BYTES` | Upload size cap |
| `ENVIRONMENT` | `development` / `production` |

Never commit `.env` files.

## OAuth and YouTube tokens

- Use official Google OAuth 2.0 only.
- Store refresh tokens **encrypted** (`youtube_accounts.refresh_token_encrypted`).
- Do not store Google passwords.
- Restrict OAuth scopes to the minimum required for upload, thumbnails, playlists, and channel read.
- Secure callback endpoint; validate `state` parameter.

## n8n

- Self-hosted inside Docker network.
- Protect editor UI with basic auth / n8n auth.
- Authenticate all webhooks to FastAPI with shared secret or HMAC + timestamp skew window.
- Do not expose n8n ports publicly without auth in production.
- Import workflows as files; avoid embedding secrets in workflow JSON (use n8n credentials store).

## Media and file safety

- Validate MIME types, extensions, and file size on all uploads.
- Generate safe filenames; reject path traversal (`..`, absolute paths).
- Serve files only via authenticated media endpoints using asset IDs — **never** expose raw filesystem paths to clients.
- Shared Docker volume between backend and worker with least privilege where practical.
- Retention/cleanup policies must not delete before verified YouTube publication.

## FFmpeg / subprocess

- Execute with argument arrays only (`subprocess` list form).
- Never interpolate user-controlled strings into a shell command.
- Bound timeouts and output paths to the project storage directory.
- Validate inputs with FFprobe before render.

## API hardening

- Pydantic/Zod validation on all inputs.
- CORS restricted to known frontend origins.
- Rate limiting on auth, generation, and publish endpoints.
- Structured logging without secrets or full credential material.
- Audit log for approvals, publishes, settings changes, and cleanup.
- Consistent error responses that do not leak stack traces in production.

## Frontend

- No provider secrets in Vite env for client bundles (only public API base URL).
- Use HTTPS in production deployments.
- CSRF protections if cookie sessions are used.

## Operational

- Health endpoints without sensitive detail.
- Dependency and base image updates as part of maintenance.
- Separate development vs production Compose configs when secrets differ.

## Threat notes specific to this product

| Risk | Mitigation |
| --- | --- |
| Duplicate paid Suno/Higgsfield charges | Idempotency keys + provider status reconciliation before retry |
| Duplicate YouTube uploads | Publication row + video ID checks + idempotency |
| Premature media deletion | Cleanup gated on `publication_verified_at` |
| Prompt injection into shell | No shell; argv only; path sandbox |
| Cost runaway | Budget gates before enqueue |
| Unofficial Suno clients | Explicitly forbidden in architecture |

## Related

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`PROVIDER_INTEGRATIONS.md`](PROVIDER_INTEGRATIONS.md)
- [`N8N_WORKFLOWS.md`](N8N_WORKFLOWS.md)
