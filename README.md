# Ragam Spiritual

Autonomous AI-powered Telugu devotional YouTube production platform.

**Week schedule** (auto deity by weekday + festive mood by month) → **Create song + 2 Shorts** → Cursor lyrics → Suno Pro upload → thumbnail (logo + deity + title) → publish main + Shorts together.

See [docs/AUTONOMOUS_WEEKLY_WORKFLOW.md](docs/AUTONOMOUS_WEEKLY_WORKFLOW.md).

**Current music path:** manual Suno upload (subscription-safe). Optional API providers remain configured for later.

## Current status

**Phase 1 in progress** — Docker infrastructure scaffold with provider config wired from `.env`.

## Provider stack (locked)

| Concern | Choice |
| --- | --- |
| LLM / Lyrics | **Gemini** (`gemini-3.8-flash`) — deep Telugu keerthana + Suno style |
| Thumbnails | **Gemini Image** ultra-premium still (ChatGPT-class); 3D Telugu + logo local; Kling Omni fallback |
| Music | **Mureka** official API (`MUREKA_API_KEY`); `/api/v1/music/*` — validate Telugu vocals |
| Video | **Gemini → Kling 4.0** (`VIDEO_PROVIDER=auto`, 720p silent); auto prep **1h before** `publish_at`, auto YouTube at schedule; Shorts cut from same clip |
| YouTube | Google OAuth (channel connected) |

## Secrets

Single source of truth: **`.env`** (gitignored). Template: [`.env.example`](.env.example).

`mykeys.md`, `api-keys.md`, and `client_secret*.json` are gitignored — do not commit them.

## Quick start

```bash
cp .env.example .env   # if needed; project already has a local .env
docker compose up --build
```

### Local URLs

| Service | URL |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8010 |
| API docs | http://localhost:8010/docs |
| Health | http://localhost:8010/health |
| Ready | http://localhost:8010/ready |
| n8n (optional profile) | `docker compose --profile full up -d n8n` → http://localhost:5678 |
| Postgres | localhost:5435 |
| Redis | localhost:6381 |

Host ports avoid conflicts with other local stacks. n8n is under Compose profile `full` (large image).

Smoke Celery job:

```bash
curl -X POST http://localhost:8010/api/v1/jobs/smoke -H 'Content-Type: application/json' -d '{"message":"hello"}'
```


## Documentation

| Document | Description |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Phased plan |
| [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) | Schema |
| [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md) | REST contracts |
| [docs/PROVIDER_INTEGRATIONS.md](docs/PROVIDER_INTEGRATIONS.md) | AIMLAPI / Cursor / YouTube |
| [docs/N8N_WORKFLOWS.md](docs/N8N_WORKFLOWS.md) | Orchestration |
| [docs/SECURITY.md](docs/SECURITY.md) | Security |

## Next phases

- Phase 2: DB schema + Song Studio CRUD  
- Phase 3+: Cursor lyrics, AIMLAPI music/video, FFmpeg, YouTube publish, n8n workflows  
