# Implementation Plan

Phased delivery for the autonomous Telugu devotional YouTube production platform.

**Rule:** Implement only the currently approved phase. After each phase: run services/tests, fix errors, update docs, summarize, and wait for approval before the next phase.

Source requirements: [`project-plan-promt.md`](../project-plan-promt.md).

---

## Phase 0 — Architecture and API feasibility

**Status:** Complete. Waiting for approval before Phase 1.

### Deliverables

- [x] Inspect repository
- [x] [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [x] [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) (this file)
- [x] [`DATABASE_DESIGN.md`](DATABASE_DESIGN.md)
- [x] [`API_SPECIFICATION.md`](API_SPECIFICATION.md)
- [x] [`PROVIDER_INTEGRATIONS.md`](PROVIDER_INTEGRATIONS.md)
- [x] [`N8N_WORKFLOWS.md`](N8N_WORKFLOWS.md)
- [x] [`SECURITY.md`](SECURITY.md)
- [x] Root [`README.md`](../README.md)

### Exit criteria

- Architecture, DB, API, providers, n8n, and security documented.
- Confirmed vs account-dependent vs manual-fallback capabilities clearly labeled.
- No application code required.
- **Human approval required before Phase 1.**

---

## Phase 1 — Infrastructure

**Status:** Complete and verified locally (`docker compose up --build`; health/ready/smoke job OK). n8n optional via `--profile full`.

### Build

- [x] React + TypeScript + Vite + Tailwind scaffold (shadcn deferred to Phase 2 UI polish)
- [x] FastAPI app skeleton with health / ready / provider status endpoints
- [x] PostgreSQL, Redis, Celery worker, Celery Beat, n8n
- [x] Dockerfiles + `docker-compose.yml` + `.env.example` + local `.env`
- [x] Named volumes (postgres, n8n, media)
- [x] FFmpeg/FFprobe in backend/worker image
- [x] Health checks and service dependency order
- [x] README local URLs
- [x] Provider stack locked: Cursor LLM + AIMLAPI music/video + YouTube OAuth env

### Exit criteria

- `docker compose up --build` starts all services successfully.
- Frontend, API health, Postgres, Redis, n8n reachable at documented URLs.
- Workers consume a smoke Celery task.
- **Human approval required before Phase 2.**

---

## Phase 2 — Core application

### Build

- Alembic migrations for core tables (users, categories, song projects, settings, audit basics)
- Song project CRUD APIs
- Auth (secure password hashing + JWT or secure sessions)
- Dashboard shell with navigation modules
- Song Studio UI wired to FastAPI
- TanStack Query + Zustand + React Hook Form + Zod patterns established
- Devotional categories seeded / configurable

### Exit criteria

- Create/list/update/delete song projects via API and UI.
- Dashboard shows empty/zero-state metrics from real DB queries.
- Migrations apply cleanly on fresh Compose stack.
- **Human approval required before Phase 3.**

---

## Phase 3 — Autonomous content generation

### Build

- `LLMProvider` / `CursorLLMProvider` (default via `cursor-sdk` + `CURSOR_API_KEY`; model default `composer-2.5`)
- Optional `OpenAIProvider` secondary LLM only if needed later
- Telugu lyrics generation + lyric-quality evaluation stage
- Lyrics versioning, edit, approve/reject APIs and Lyrics Studio
- Prompt templates for music, visual, and YouTube metadata
- Cost/usage records for Cursor LLM (best-effort from SDK)
- Optional OpenAI Images path for thumbnails when key present
- Budget pre-flight hooks (even if other providers not live yet)

### Exit criteria

- Generate, validate, edit, version, and approve Telugu lyrics end-to-end.
- Music/visual/YouTube text prompts generated without inventing provider params.
- Never silently alter user-approved lyrics.
- **Human approval required before Phase 4.**

---

## Phase 4 — Autonomous music generation

### Build

- `MusicProvider` interface
- `SunoOfficialProvider` **only after** signed-in Platform docs are available
- Async job create/status/retrieve via Celery
- Audio validation (duration, format) via FFprobe
- Candidate comparison when API supports multiple outputs
- Cost tracking when provider exposes it
- `ManualAudioUploadProvider` emergency fallback
- Music Studio UI (progress, preview, approve)

### Exit criteria

- Happy path works with official Suno **or** clearly reports unavailable access while manual upload works.
- No unofficial/scraped Suno integrations.
- Jobs resumable; no blind duplicate paid generations.
- **Human approval required before Phase 5.**

---

## Phase 5 — Autonomous visual generation

### Build

- `VideoProvider` / `HiggsfieldProvider` (default model: Cinema Studio 4.0, 10s, 16:9)
- Visual prompt generation
- Async submit + poll/webhook + download to local volume
- Clip validation; `generate_audio: false` for looping under song audio
- `ManualVideoUploadProvider` fallback
- Visual Studio UI

### Exit criteria

- One ~10s clip generated and stored per song on success.
- Manual upload path works if API credentials missing.
- Idempotent retries with external status reconciliation.
- **Human approval required before Phase 6.**

---

## Phase 6 — Video rendering

### Build

- FFmpeg rendering service (argv arrays, no shell interpolation)
- Loop visual to audio duration with discontinuity minimization
- Scale/crop to 1920×1080, optional logo/title overlays
- H.264 + AAC MP4 output matching audio duration
- Progress, cancel, retry, validation report, preview
- Thumbnail composition (image + Telugu title text overlay)
- Renderer UI

### Exit criteria

- Final MP4 validates with FFprobe; duration matches audio.
- Retries reuse approved assets (no re-billing visual/music).
- CPU fallback works without requiring GPU.
- **Human approval required before Phase 7.**

---

## Phase 7 — YouTube publishing

### Build

- Google OAuth 2.0 connect + encrypted refresh token storage
- Channel info, playlists
- Resumable upload, metadata, thumbnail, playlist add
- Schedule via `privacyStatus=private` + `publishAt`
- Publication verification before cleanup
- Quota-aware throttling (~100 uploads/day default bucket)
- Approval-before-publish default; auto-publish setting
- Cleanup Celery task (idempotent)

### Exit criteria

- Upload → verify → cleanup path proven against a test channel (or mocked integration tests + documented live checklist).
- Failed upload does not delete local media.
- Duplicate upload prevention via idempotency / prior publication record.
- **Human approval required before Phase 8.**

---

## Phase 8 — n8n automation

### Build

- Importable Workflow A (complete production)
- Workflow B (error handling / retry)
- Workflow C (scheduled publishing)
- Workflow D (recovery on restart)
- Authenticated webhooks to FastAPI only
- Approval gates and resume-from-stage
- Automation UI visibility into execution status

### Exit criteria

- End-to-end autonomous run from song start to verified publish (with approvals as configured).
- Failure at mid-stage resumes without regenerating successful paid assets.
- n8n contains no duplicated business logic.
- **Human approval required before Phase 9.**

---

## Phase 9 — Analytics and optimization

### Build

- YouTube Analytics API integration (official metrics only)
- Performance dashboard by category
- Cost monitoring dashboards (song / provider / month)
- Optional feedback into templates (titles, thumbnails, publish times) — no fabricated metrics

### Exit criteria

- Real analytics displayed where API grants access; gaps labeled clearly.
- Cost views reconcile with `cost_records`.
- Platform considered feature-complete for v1 goals.

---

## Cross-phase engineering rules

1. Inspect existing code before overwriting.
2. Do not generate the entire application in one giant operation.
3. TypeScript strict; Python type hints.
4. Environment-based secrets; never commit `.env`.
5. Do not invent third-party API functionality or use unofficial integrations.
6. Do not use cloud object storage.
7. Do not delete media before verified publication.
8. Frontend is not responsible for background processing.
9. Document every integration and environment variable.
10. Prefer reuse of approved assets on retry.

## Account blockers (owner actions)

Complete before or during the relevant phase:

1. **Suno Platform** — sign in, capture official API reference (auth, generate, status, download, custom lyrics, commercial terms).
2. **Higgsfield Console** — API key id/secret, model entitlement, 10s 720p pricing.
3. **Google Cloud** — OAuth client + YouTube Data API for target channel.

## Phase gate template

After each phase, deliver:

1. Summary of completed features  
2. How to run / verify  
3. Test results  
4. Known limitations  
5. Outstanding tasks  
6. Explicit ask: approve Phase N+1?
