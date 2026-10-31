# API Specification

Base path: `/api/v1`  
Format: JSON  
Auth: Bearer JWT (or session cookie — see [`SECURITY.md`](SECURITY.md)); n8n uses a dedicated service credential / webhook HMAC.

All long-running operations return a **job ID** immediately and expose status via job endpoints.

---

## Common conventions

### Success envelope

```json
{
  "data": {},
  "meta": {}
}
```

List responses:

```json
{
  "data": [],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 0
  }
}
```

### Error envelope

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable summary",
    "details": []
  }
}
```

Suggested HTTP mapping:

| Status | Use |
| --- | --- |
| 400 | Validation / bad input |
| 401 | Unauthenticated |
| 403 | Forbidden |
| 404 | Not found |
| 409 | Conflict (duplicate idempotency, invalid state transition) |
| 422 | Semantic validation |
| 429 | Rate / budget / YouTube quota |
| 502/503 | Upstream provider unavailable |

### Pagination and filters

- Query: `page`, `page_size` (max 100), `sort`, `order`
- Common filters: `status`, `category_id`, `deity`, `created_from`, `created_to`

### Idempotency

Optional header: `Idempotency-Key` on paid generation and publish endpoints. Server stores key on `generation_jobs.idempotency_key`.

### Async job shape

```json
{
  "data": {
    "job_id": "uuid",
    "status": "queued",
    "job_type": "music",
    "song_id": "uuid",
    "progress_percent": 0
  }
}
```

---

## Health (non-versioned or `/api/v1/health`)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (DB + Redis) |

---

## Auth

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Create user (disable in prod if single-tenant) |
| POST | `/api/v1/auth/login` | Obtain token |
| POST | `/api/v1/auth/logout` | Invalidate session if used |
| GET | `/api/v1/auth/me` | Current user |

---

## Song projects

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/songs` | Create song project |
| GET | `/api/v1/songs` | List / filter projects |
| GET | `/api/v1/songs/{song_id}` | Detail including current stage summary |
| PATCH | `/api/v1/songs/{song_id}` | Update configuration |
| DELETE | `/api/v1/songs/{song_id}` | Archive or delete per policy |

**POST body (illustrative):** topic, title, deity, category_id, language, lyrics_style, lyrical_structure, charanam_count, include_slokam, music_genre, vocal_preference, instruments, target_duration_seconds, visual_style, youtube_settings, approval_mode, budget_limit, template_id.

---

## Lyrics

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/songs/{song_id}/lyrics/generate` | Start lyrics generation job |
| GET | `/api/v1/songs/{song_id}/lyrics` | List versions |
| GET | `/api/v1/lyrics/{lyrics_id}` | Single version |
| PATCH | `/api/v1/lyrics/{lyrics_id}` | Edit (creates new version or updates draft — prefer new version after approval) |
| POST | `/api/v1/lyrics/{lyrics_id}/approve` | Approve |
| POST | `/api/v1/lyrics/{lyrics_id}/reject` | Reject with reason |
| POST | `/api/v1/lyrics/{lyrics_id}/evaluate` | Run quality evaluation |

Approved lyrics must never be silently rewritten by generation jobs.

---

## Music

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/songs/{song_id}/music-prompt/generate` | Generate music-style prompt from approved lyrics |
| POST | `/api/v1/songs/{song_id}/music/generate` | Start Suno (or configured) generation |
| POST | `/api/v1/songs/{song_id}/music/upload` | Manual audio fallback |
| GET | `/api/v1/songs/{song_id}/music` | List generations / candidates |
| GET | `/api/v1/music/jobs/{job_id}` | Job status |
| POST | `/api/v1/music/jobs/{job_id}/retry` | Retry with reconciliation |
| POST | `/api/v1/music/{generation_id}/approve` | Approve candidate |

Returns `409` if lyrics not approved. Returns `429` if budget exceeded.

---

## Visuals

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/songs/{song_id}/visual-prompt/generate` | Generate visual prompt |
| POST | `/api/v1/songs/{song_id}/visuals/generate` | Start Higgsfield 10s generation |
| POST | `/api/v1/songs/{song_id}/visuals/upload` | Manual visual fallback |
| GET | `/api/v1/songs/{song_id}/visuals` | List visuals |
| GET | `/api/v1/visuals/jobs/{job_id}` | Job status |
| POST | `/api/v1/visuals/{generation_id}/approve` | Approve clip |

Default generation parameters (server-side): duration 10, aspect 16:9, `generate_audio: false`, Cinema Studio 4.0 unless overridden in provider config.

---

## Thumbnails

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/songs/{song_id}/thumbnail/generate` | Generate background + compose Telugu title |
| GET | `/api/v1/songs/{song_id}/thumbnail` | Latest / list thumbnails |
| POST | `/api/v1/thumbnails/{thumbnail_id}/regenerate` | Regenerates within attempt budget |

Target: 16:9, preferably 1280×720 output after composition.

---

## Rendering

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/songs/{song_id}/render` | Enqueue FFmpeg render |
| GET | `/api/v1/songs/{song_id}/render` | Latest render status / history |
| GET | `/api/v1/jobs/{job_id}` | Generic job status (render and others) |
| POST | `/api/v1/jobs/{job_id}/cancel` | Cancel if supported |

Requires approved audio + visual assets.

---

## YouTube

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/youtube/auth` | Start OAuth |
| GET | `/api/v1/youtube/callback` | OAuth callback |
| GET | `/api/v1/youtube/channel` | Connected channel |
| GET | `/api/v1/youtube/playlists` | List playlists |
| POST | `/api/v1/songs/{song_id}/publish` | Upload now (respects approval settings) |
| POST | `/api/v1/songs/{song_id}/schedule` | Schedule publish_at |
| GET | `/api/v1/songs/{song_id}/publication` | Publication + processing status |
| POST | `/api/v1/songs/{song_id}/publication/verify` | Re-check YouTube processing |
| POST | `/api/v1/songs/{song_id}/cleanup` | Manual cleanup trigger (after verify) |

Publish endpoints enqueue Celery work and return `job_id`.

---

## Workflow

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/v1/workflows/songs/{song_id}/start` | Create execution + trigger n8n Workflow A |
| GET | `/api/v1/workflows/{execution_id}` | Execution detail |
| POST | `/api/v1/workflows/{execution_id}/retry` | Retry failed stage |
| POST | `/api/v1/workflows/{execution_id}/resume` | Resume from `resume_from_stage` |
| POST | `/api/v1/workflows/internal/{stage}` | **n8n-only** authenticated stage commands (optional consolidation) |

Stage command endpoints used by n8n may also call the domain endpoints above directly; prefer domain endpoints so business logic stays in FastAPI.

Suggested n8n-facing helpers (optional, same auth):

- `POST /api/v1/internal/songs/{song_id}/stages/lyrics`
- `POST /api/v1/internal/songs/{song_id}/stages/music`
- `POST /api/v1/internal/songs/{song_id}/stages/visual`
- `POST /api/v1/internal/songs/{song_id}/stages/thumbnail`
- `POST /api/v1/internal/songs/{song_id}/stages/render`
- `POST /api/v1/internal/songs/{song_id}/stages/metadata`
- `POST /api/v1/internal/songs/{song_id}/stages/publish`
- `POST /api/v1/internal/songs/{song_id}/stages/verify`
- `POST /api/v1/internal/songs/{song_id}/stages/cleanup`
- `GET /api/v1/internal/jobs/{job_id}/wait-status` — poll helper for n8n

---

## Dashboard / analytics (app metrics)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/dashboard/summary` | Counts: songs, in progress, failed, costs, upcoming schedule |
| GET | `/api/v1/dashboard/activity` | Recent production activity |
| GET | `/api/v1/costs` | Cost records / rollups |
| GET | `/api/v1/analytics/youtube` | Phase 9 — official Analytics API only |

---

## Settings and templates

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/settings` | System settings |
| PATCH | `/api/v1/settings` | Update settings |
| GET | `/api/v1/categories` | Devotional categories |
| POST/PATCH | `/api/v1/categories` | Manage categories |
| GET/POST/PATCH | `/api/v1/prompt-templates` | Prompt / song templates |
| GET/PATCH | `/api/v1/providers` | Provider enablement (no raw secrets) |

---

## Media access

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v1/media/{asset_id}` | Authenticated stream/download |
| GET | `/api/v1/songs/{song_id}/media` | List assets for project |

Never return absolute host filesystem paths. Use asset IDs and signed/authenticated routes.

---

## OpenAPI

FastAPI will expose interactive OpenAPI at `/docs` and `/redoc` in development. This markdown remains the product contract for Phase 0; implementations should stay aligned and update this file when routes change.
