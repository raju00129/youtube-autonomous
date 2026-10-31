# Provider Integrations

## Locked stack

| Concern | Provider | Notes |
| --- | --- | --- |
| Text LLM | Cursor (`composer-2.5`) | Lyrics, prompts, metadata |
| Thumbnails | Cursor Agent GenerateImage (`composer-2.5`) | Telugu title composited locally |
| **Music** | **Mureka** (official API) | Custom lyrics; ~`$0.03`–`$0.045`/song; commercial rights. Telugu not in FAQ list — test. |
| Video | Google Gemini Omni Flash (`gemini-omni-1.1-flash`) | 10s / **720p** / 16:9; Shorts ffmpeg-cut from same clip |
| YouTube | Google OAuth | Channel connected |

---

## Why not official Suno?

Suno Support confirmed (2026):

- No self-serve public API / keys / docs yet
- Consumer Pro ≠ Platform account (`No platform account` is expected)
- Apply here: https://sunomusic.typeform.com/apiform (invite / expression of interest, no timeline)

`sunoapi.org` is a third-party reseller (separate billing, not your Suno sub). We moved off it.

## Why not Mureka as primary?

[Mureka](https://platform.mureka.ai/) is a solid official music API (~`$0.03`–`$0.045`/song, commercial rights) but FAQ languages are **zh / en / ja / ko / pt / es / de / fr / it / ru** — **Telugu is not listed**. Keep as a future quality option if ACE-Step Telugu vocals disappoint.

---

## Music: WaveSpeed ACE-Step 1.5

- Playground / model: https://wavespeed.ai/models/wavespeed-ai/ace-step-1.5
- Base URL: `https://api.wavespeed.ai`
- Auth: `Authorization: Bearer ${WAVESPEED_API_KEY}`
- Submit: `POST /api/v3/wavespeed-ai/ace-step-1.5`
- Poll: `GET /api/v3/predictions/{id}/result`
- Inputs: `tags` (style), `lyrics` (optional), `duration` (≤240s), `seed`
- Pricing (list): ~`$0.0003` per second → ~`$0.036` for 2 minutes

### Signup

1. Register at https://wavespeed.ai/
2. Create an API key
3. Put it in `.env` as `WAVESPEED_API_KEY=...` (or `wavespeed: ...` in `mykeys.md`)
4. Restart backend + worker — readiness should show `wavespeed_music: true`

### App endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/music/status` | Provider configured? |
| POST | `/api/v1/music/generate` | Submit → `task_id` (`wait: true` = Celery poll) |
| GET | `/api/v1/music/tasks/{task_id}` | Poll prediction |

Implementation: `backend/app/providers/wavespeed_music.py`.

---

## Cursor / Gemini / YouTube

Unchanged: Cursor for LLM+thumbs; Gemini for video; YouTube OAuth for publish.
