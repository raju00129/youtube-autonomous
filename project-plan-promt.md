# MASTER PROJECT PROMPT
# Autonomous AI-Powered Telugu Devotional YouTube Production Platform

Act as a Principal Software Architect, Senior Full-Stack Engineer, AI Integration Engineer and DevOps Engineer.

Your responsibility is to design and build a production-ready autonomous AI-powered YouTube devotional music production platform.

The system must autonomously create Telugu devotional songs, generate music, generate devotional visuals, render complete videos, create thumbnails, prepare YouTube metadata, upload videos and schedule publication.

This is not a simple CRUD application. It is an autonomous media production operating system with workflow orchestration, background processing, external AI integrations, monitoring, retries and publishing automation.

The application should be modular, scalable, maintainable, cost-conscious and suitable for running locally through Docker initially.

---

# 1. PRODUCT VISION

Build an application that can autonomously produce multiple devotional music videos with minimal human intervention.

The user should be able to configure:

- Song topic.
- Deity or devotional category.
- Language.
- Lyrics style.
- Chandassu or lyrical structure.
- Music genre.
- Vocal preference.
- Musical instruments.
- Video visual style.
- YouTube publishing settings.
- Publication schedule.
- Automation and approval preferences.

Once the production workflow is started, the system should execute all available stages automatically.

## Expected production workflow

1. Generate devotional song concepts.
2. Generate Telugu lyrics.
3. Validate lyrics and spelling.
4. Generate music-generation instructions.
5. Generate music through the official Suno API, subject to account/API access.
6. Retrieve the completed audio automatically.
7. Validate the generated audio.
8. Generate a devotional video prompt.
9. Generate one meaningful 10-second video using Higgsfield or another configured provider.
10. Generate a YouTube thumbnail.
11. Generate YouTube title, description, tags and playlist suggestions.
12. Render the complete video using FFmpeg.
13. Validate the final video.
14. Upload the video to YouTube.
15. Set metadata and thumbnail.
16. Add the video to the appropriate playlist.
17. Schedule or publish the video.
18. Verify successful YouTube processing and publication.
19. Delete temporary media files from local storage.
20. Retain production metadata, costs and publishing history.

## Critical video-generation requirement

For regular devotional songs:

- Generate only ONE meaningful 10-second video clip per song.
- Loop that clip to match the complete song duration.
- Do not generate scene-by-scene videos.
- Do not synchronize visuals to individual lyrics or music beats.
- Do not generate unnecessary video scenes.
- Do not add expensive video-generation stages.
- Generate footage with a visually suitable loop and minimal discontinuity.
- Do not embed text in generated visuals.
- Do not embed channel logos in generated visuals; add branding during FFmpeg rendering.

The separate Ramayana cinematic movie project may eventually use a premium multi-scene production workflow. Keep this platform extensible enough to support that later, but do not implement it in the initial release.

---

# 2. TECHNOLOGY STACK

Use the following technologies.

## Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- React Router
- TanStack Query
- Zustand
- React Hook Form
- Zod
- Lucide icons

Use a premium, modern studio-style admin dashboard.

Support both dark and light themes.

## Backend

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy 2.x
- Alembic
- PostgreSQL

## Workflow orchestration

- Self-hosted n8n
- Celery
- Redis

Responsibilities:

n8n:
- Orchestrate the production lifecycle.
- Trigger workflows.
- Coordinate workflow stages.
- Manage approval waits.
- Coordinate scheduled publishing.
- Handle notifications and failure-routing.

FastAPI:
- Core business logic.
- REST APIs.
- Authentication.
- Provider integrations.
- Database operations.
- Workflow initiation.
- Media management.

Celery:
- Long-running background operations.
- Music-generation status tracking.
- Video-generation status tracking.
- FFmpeg rendering.
- YouTube uploads.
- File cleanup.

Redis:
- Celery broker.
- Task coordination.
- Short-lived cache.

Do not duplicate business logic in n8n.

n8n should orchestrate operations through authenticated FastAPI endpoints.

## Media processing

- FFmpeg
- FFprobe
- Local filesystem storage.

## External providers

- OpenAI API.
- Official Suno API.
- Higgsfield API.
- Google YouTube Data API v3.
- YouTube Analytics API.

## Infrastructure

- Docker.
- Docker Compose.
- PostgreSQL.
- Redis.
- n8n.
- Local named Docker volumes.

Do not introduce Kubernetes or microservices in the initial version.

---

# 3. SYSTEM ARCHITECTURE

Use a modular monolith architecture.

The application should have these layers:

React Admin Dashboard
    |
    v
FastAPI Application
    |
    +---- PostgreSQL
    |
    +---- n8n Workflow Orchestration
    |
    +---- Celery Background Workers
                |
                +---- OpenAI
                +---- Suno
                +---- Higgsfield
                +---- FFmpeg
                +---- YouTube API
                +---- Local Media Storage

Redis coordinates background jobs.

PostgreSQL stores metadata and execution history.

Local filesystem stores temporary media.

Do not use AWS S3, Azure Blob Storage, Google Cloud Storage or any other object-storage service.

The application should be capable of running entirely on a local Docker environment, apart from calls to external AI and YouTube APIs.

---

# 4. REACT FRONTEND

Build a complete production management dashboard.

## Navigation modules

1. Dashboard
2. Song Studio
3. Lyrics Studio
4. Music Studio
5. Visual Studio
6. Thumbnail Studio
7. Video Renderer
8. Publishing Calendar
9. YouTube Channel
10. Playlists
11. Analytics
12. Automation
13. Generation History
14. Cost Monitoring
15. Settings

## Dashboard

Show:

- Total songs created.
- Songs in progress.
- Lyrics generated.
- Music generation jobs.
- Videos generated.
- Videos rendered.
- Published videos.
- Scheduled videos.
- Failed jobs.
- Current production costs.
- Recent production activity.
- Upcoming publication schedule.

Provide filters by date, category, deity and production status.

## Song Studio

Allow the user to:

- Create a song project.
- Enter song title or topic.
- Select deity.
- Select devotional category.
- Select language.
- Select lyrical style.
- Select lyrical structure.
- Configure number of charanams.
- Configure slokam inclusion.
- Select musical genre.
- Select voice preference.
- Select instruments.
- Set desired song duration.
- Generate lyrics.
- Regenerate lyrics.
- Edit lyrics.
- Save versions.
- Approve lyrics.
- Start music generation.

Support reusable song templates.

Suggested devotional categories:

- Vishnu.
- Shiva.
- Lakshmi.
- Durga.
- Saraswati.
- Hanuman.
- Narasimha.
- Venkateswara.
- Rama.
- Krishna.
- Ganesha.
- Subrahmanya.
- Other devotional topics.

Make categories configurable through the database.

## Lyrics Studio

Build an advanced Telugu lyrics editor.

Requirements:

- Unicode Telugu support.
- Pallavi section.
- Anupallavi section where applicable.
- Charanam sections.
- Slokam section.
- Lyrics version history.
- Edit and regenerate.
- Approve and reject.
- Compare versions.
- Save source references for traditional slokas.

Quality requirements:

- Correct Telugu spelling.
- Correct Telugu grammar.
- Natural pronunciation.
- Meaningful devotional vocabulary.
- Appropriate lyrical meter and rhythm.
- Avoid unnatural or fabricated Telugu expressions.
- Avoid unnecessary repetition.
- Avoid incorrectly quoted Sanskrit slokas.
- Never silently alter user-approved lyrics.

Use a separate lyric-quality evaluation stage.

Where exact traditional slokas are requested, prefer trusted source text supplied by the user or a verified reference. Do not fabricate citations or claim unverified text is scripturally authentic.

## Music Studio

This module must support autonomous music generation through the official Suno API.

Requirements:

- Display approved lyrics.
- Generate music-style prompts.
- Configure music-generation parameters.
- Submit music-generation requests.
- Track asynchronous generation.
- Show generation progress.
- Retrieve generated audio.
- Support multiple candidates where the API supports them.
- Allow candidate comparison.
- Allow regeneration.
- Preview audio.
- Validate duration.
- Store generation metadata.
- Store provider request IDs.
- Track estimated and actual costs when available.
- Approve the final audio.

Support vocal, instrumental, genre and style parameters according to actual provider capabilities.

Do not invent Suno API parameters.

### Suno API integration rules

Official platform:

https://platform.suno.com/

Before implementation:

1. Inspect official documentation.
2. Confirm API availability for the user's account.
3. Verify authentication.
4. Verify generation endpoints.
5. Verify supported models.
6. Verify custom lyrics support.
7. Verify voice and style configuration.
8. Verify callbacks or webhooks.
9. Verify task-status endpoints.
10. Verify audio retrieval and download.
11. Verify usage limits and costs.
12. Verify commercial-use and monetization permissions.

Implement a provider adapter.

MusicProvider interface:

- generate_song()
- get_generation_status()
- get_generated_audio()
- cancel_generation(), only if supported

Implement:

- SunoOfficialProvider.
- ManualAudioUploadProvider as an emergency fallback.

Autonomous generation must be the normal workflow.

Do not use:
- Unofficial APIs.
- Private endpoints.
- Session-cookie extraction.
- Browser scraping.
- Browser automation.
- Reverse-engineered authentication.

If official API access is unavailable, report it clearly and keep the provider interface ready. Do not pretend music generation is working when it is not.

---

# 5. AUTONOMOUS VISUAL GENERATION

Use Higgsfield as the initial preferred provider, subject to official API access.

Official website:

https://higgsfield.ai/

Generate exactly one meaningful 10-second visual per regular devotional song.

Visual-generation configuration:

- Deity.
- Devotional theme.
- Temple environment.
- Divine lighting.
- Camera movement.
- Background atmosphere.
- Flowers, lamps and decorative elements.
- Aspect ratio.
- Duration.
- Visual quality.

Example:

Lord Vishnu standing in a magnificent ancient South Indian temple, divine golden illumination, subtle movement of flower petals, glowing oil lamps, gentle cinematic camera movement, rich traditional devotional atmosphere, highly detailed visual composition, no text, no logos, designed for seamless looping.

Video provider interface:

- generate_video()
- get_generation_status()
- get_generated_video()
- cancel_generation(), only if supported.

Implement:

- HiggsfieldProvider.
- ManualVideoUploadProvider as fallback.

Before implementation, verify official API documentation, available models, API authentication, pricing, generation duration, aspect ratio, callbacks and downloadable output.

Do not invent endpoints or use unauthorized API integrations.

If Higgsfield API access is unavailable, preserve the modular provider architecture and report the limitation.

---

# 6. THUMBNAIL GENERATION

Generate professional YouTube thumbnails.

Use OpenAI image generation or another configurable image provider.

Requirements:

- 16:9 aspect ratio.
- 1280x720 output where supported.
- Premium devotional visual.
- Correct deity representation.
- High visual contrast.
- Proper title placement.
- Channel branding.
- Telugu title text rendered separately from the generated image.
- Preview and editing.
- Regeneration.
- File validation.

Do not rely on image-generation models to render accurate Telugu text.

Generate the background image first, then add correctly spelled Telugu title text using an image-composition service.

Allow reusable thumbnail templates for devotional categories.

---

# 7. FFmpeg VIDEO RENDERING ENGINE

Implement a dedicated video-rendering service.

Input:

- Approved audio file.
- One generated 10-second video clip.
- Thumbnail.
- Optional channel logo.
- Song title.
- Rendering configuration.

Output:

- MP4.
- H.264 video.
- AAC audio.
- 1920x1080.
- 16:9.
- Duration matching the song audio.

Processing:

1. Validate audio using FFprobe.
2. Validate video using FFprobe.
3. Determine actual audio duration.
4. Determine actual video duration.
5. Loop the visual to cover the audio duration.
6. Use suitable looping techniques to minimize visible jumps.
7. Scale and crop to 1920x1080.
8. Add optional logo overlay.
9. Add optional title overlay.
10. Combine video and audio.
11. Ensure final duration matches the audio.
12. Validate the final MP4.
13. Generate a rendering report.

Use hardware acceleration only when available.

Provide CPU fallback.

Use safe FFmpeg subprocess execution with argument arrays. Never concatenate user-controlled text into shell commands.

Add:
- Rendering progress.
- Render cancellation.
- Retry.
- Failure logs.
- Output validation.
- Preview support.

Do not regenerate visuals during rendering retries.

Reuse existing approved assets whenever possible.

---

# 8. LOCAL MEDIA STORAGE — NO CLOUD STORAGE

All generated media must remain in local temporary storage.

Do not use:
- AWS S3.
- Azure Blob Storage.
- Google Cloud Storage.
- Any external object storage.

Suggested structure:

/app/storage/
    temp/
        {song_id}/
            lyrics.txt
            audio.mp3
            visual.mp4
            thumbnail.jpg
            final-video.mp4
    logs/
    cache/

Use a Docker named volume shared by the FastAPI backend and Celery workers.

Implement MediaStorageService.

Responsibilities:

- Create project directories.
- Save generated audio.
- Save generated videos.
- Save thumbnails.
- Save rendered videos.
- Validate MIME types.
- Validate file extensions.
- Validate file size.
- Generate safe filenames.
- Provide controlled file access.
- Delete temporary assets.
- Recover abandoned jobs.
- Enforce retention policies.

## Cleanup policy

After successful YouTube publication:

1. Verify the YouTube upload is complete.
2. Save the YouTube video ID in PostgreSQL.
3. Check YouTube processing status.
4. Verify metadata.
5. Verify thumbnail update.
6. Record publication status.
7. Trigger a dedicated cleanup Celery task.
8. Delete generated audio, visual, thumbnail and final MP4 files.
9. Clear temporary file paths in PostgreSQL.
10. Preserve project metadata, lyrics and publishing history according to retention settings.

Never delete files immediately after an upload request.

If any stage fails, preserve files for retry.

Implement:
- Idempotent cleanup.
- Configurable retention.
- Failed-job recovery.
- Cleanup logs.
- Manual cleanup controls.
- Option to retain files temporarily for debugging.

---

# 9. YOUTUBE INTEGRATION

Use official Google OAuth 2.0 and YouTube Data API v3.

Documentation:

https://developers.google.com/youtube/v3

Implement:

- Google OAuth connection.
- Channel authorization.
- Secure token refresh.
- Channel information retrieval.
- Video upload.
- Resumable uploads.
- Video metadata.
- Thumbnail upload.
- Playlist retrieval.
- Playlist management.
- Scheduled publishing.
- Publication status tracking.

Metadata:

- Title.
- Description.
- Tags.
- Category.
- Language.
- Playlist.
- Thumbnail.
- Visibility.
- Scheduled publication date.

Use the official YouTube Analytics API in a later phase.

Do not store Google passwords.

Store OAuth credentials securely and encrypt refresh tokens.

Respect YouTube API quotas.

Implement retry and resumable-upload handling.

For scheduling, use the official API's supported publishing fields and visibility requirements.

Do not assume an upload response means YouTube has finished processing the video.

Verify publication state before cleanup.

Keep approval-before-publishing enabled by default.

Allow users to configure automatic publication after testing.

---

# 10. N8N WORKFLOW AUTOMATION

n8n is a mandatory architectural component.

Official documentation:

https://docs.n8n.io/

Run self-hosted n8n in Docker.

Use n8n as the central production workflow coordinator.

Do not use n8n as a replacement for FastAPI, Celery or the database.

## Workflow A: Complete song production

1. Receive a new song-production trigger.
2. Create workflow execution record.
3. Request lyrics generation from FastAPI.
4. Wait for lyrics approval if approval is enabled.
5. Trigger autonomous Suno generation.
6. Wait for music generation completion.
7. Retrieve generated audio.
8. Validate audio.
9. Trigger visual prompt generation.
10. Trigger Higgsfield video generation.
11. Wait for video completion.
12. Retrieve the video clip.
13. Trigger thumbnail generation.
14. Trigger FFmpeg rendering.
15. Wait for rendering completion.
16. Generate or retrieve YouTube metadata.
17. Validate the final video.
18. Wait for final approval if configured.
19. Trigger YouTube publishing.
20. Verify YouTube processing and publication.
21. Trigger local cleanup.
22. Update project status.
23. Record production costs and execution history.

## Workflow B: Error handling

- Detect failed stages.
- Store error information.
- Distinguish retryable and non-retryable failures.
- Retry transient provider failures.
- Avoid duplicate music generation.
- Avoid duplicate video generation.
- Preserve successful intermediate assets.
- Notify the dashboard.
- Allow manual retry.
- Support workflow resumption from the failed stage.

## Workflow C: Scheduled publishing

- Find approved scheduled projects.
- Verify publication settings.
- Trigger publishing at the configured time.
- Track upload status.
- Update publication history.
- Trigger cleanup after verification.

## Workflow D: Recovery

On application restart:

- Identify incomplete workflows.
- Identify jobs with unknown external provider status.
- Reconcile provider status where possible.
- Resume safely.
- Avoid duplicate charges or duplicate YouTube uploads.

Provide importable n8n workflow JSON files.

Use authenticated webhooks.

Never expose n8n administrative credentials publicly.

---

# 11. FASTAPI REST API DESIGN

Use `/api/v1`.

## Song projects

POST /api/v1/songs
GET /api/v1/songs
GET /api/v1/songs/{song_id}
PATCH /api/v1/songs/{song_id}
DELETE /api/v1/songs/{song_id}

## Lyrics

POST /api/v1/songs/{song_id}/lyrics/generate
GET /api/v1/songs/{song_id}/lyrics
PATCH /api/v1/lyrics/{lyrics_id}
POST /api/v1/lyrics/{lyrics_id}/approve

## Music

POST /api/v1/songs/{song_id}/music-prompt/generate
POST /api/v1/songs/{song_id}/music/generate
GET /api/v1/songs/{song_id}/music
GET /api/v1/music/jobs/{job_id}
POST /api/v1/music/jobs/{job_id}/retry

## Visuals

POST /api/v1/songs/{song_id}/visual-prompt/generate
POST /api/v1/songs/{song_id}/visuals/generate
GET /api/v1/songs/{song_id}/visuals
GET /api/v1/visuals/jobs/{job_id}

## Thumbnails

POST /api/v1/songs/{song_id}/thumbnail/generate
GET /api/v1/songs/{song_id}/thumbnail

## Rendering

POST /api/v1/songs/{song_id}/render
GET /api/v1/songs/{song_id}/render
GET /api/v1/jobs/{job_id}

## YouTube

GET /api/v1/youtube/auth
GET /api/v1/youtube/callback
GET /api/v1/youtube/channel
GET /api/v1/youtube/playlists
POST /api/v1/songs/{song_id}/publish
POST /api/v1/songs/{song_id}/schedule
GET /api/v1/songs/{song_id}/publication

## Workflow

POST /api/v1/workflows/songs/{song_id}/start
GET /api/v1/workflows/{execution_id}
POST /api/v1/workflows/{execution_id}/retry
POST /api/v1/workflows/{execution_id}/resume

## Settings

GET /api/v1/settings
PATCH /api/v1/settings

Implement request validation, pagination, filtering, structured responses and consistent errors.

All long-running operations must return job IDs.

---

# 12. DATABASE DESIGN

Use PostgreSQL with SQLAlchemy 2.x and Alembic.

Create normalized tables:

1. users
2. song_projects
3. devotional_categories
4. lyrics_versions
5. music_prompts
6. music_generations
7. visual_prompts
8. visual_generations
9. thumbnail_generations
10. media_assets
11. generation_jobs
12. video_renders
13. workflow_executions
14. youtube_accounts
15. youtube_playlists
16. youtube_publications
17. prompt_templates
18. provider_configurations
19. cost_records
20. system_settings
21. audit_logs

Each entity should include appropriate:
- UUID primary key.
- Created timestamp.
- Updated timestamp.
- Status.
- Foreign keys.
- Required indexes.

Use JSONB for flexible provider configuration and generation metadata where appropriate.

Do not store media binary data in PostgreSQL.

Do not store secrets in plain text.

Track provider IDs, request metadata, estimated costs and actual costs where available.

---

# 13. PROVIDER ABSTRACTION

All external AI providers must use independent adapter interfaces.

## LLMProvider

- OpenAIProvider

## MusicProvider

- SunoOfficialProvider
- ManualAudioUploadProvider

## VideoProvider

- HiggsfieldProvider
- ManualVideoUploadProvider

## ImageProvider

- OpenAIImageProvider

## YouTubeProvider

- YouTubeDataAPIProvider

Every provider must support appropriate:

- Configuration validation.
- Authentication.
- Timeouts.
- Retry handling.
- Error normalization.
- Usage tracking.
- Cost tracking.
- Request logging.
- Mock implementations for tests.

Provider-specific code must not be scattered throughout business logic.

Never invent API endpoints, request bodies, model names or capabilities.

When documentation is unavailable, explicitly report the limitation and isolate the integration behind an adapter.

---

# 14. COST MANAGEMENT

The platform must be cost-conscious.

Track:
- OpenAI usage.
- Suno generation usage.
- Higgsfield video generation usage.
- Image generation usage.
- YouTube API quota usage.
- Rendering resource usage.

Implement:
- Cost per song.
- Cost per provider.
- Monthly production cost.
- Failed-generation cost.
- Cost comparison between candidate generations.
- Configurable maximum generation budget.

Do not automatically generate unlimited alternatives.

Allow the user to configure:
- Maximum music candidates.
- Maximum video generation attempts.
- Maximum thumbnail attempts.
- Maximum budget per song.
- Monthly budget.

Before initiating a paid generation, check configured budget limits.

Never claim precise cost when the provider does not expose it.

---

# 15. ANALYTICS

Integrate YouTube Analytics API in a later phase.

Track:

- Views.
- Watch time.
- Average view duration.
- Impressions.
- Click-through rate.
- Subscribers gained.
- Traffic sources.
- Playlist performance.
- Video performance by devotional category.

Build a performance dashboard.

Eventually use analytics to improve:
- Titles.
- Thumbnails.
- Publication times.
- Song categories.
- Music styles.

Do not use fabricated analytics or assume every metric is available immediately.

---

# 16. AUTHENTICATION AND SECURITY

Implement secure application authentication.

Requirements:

- Secure password hashing.
- JWT or secure session authentication.
- Role-based permissions where needed.
- Environment-based secrets.
- Encrypted OAuth tokens.
- File upload validation.
- File size limits.
- Safe filename generation.
- Rate limiting.
- CORS configuration.
- Input validation.
- Secure subprocess execution.
- Structured logging.
- Audit history.
- Secure n8n webhook authentication.

Never expose API keys to the React frontend.

Never expose internal file-system paths.

Never commit .env files.

Provide `.env.example`.

---

# 17. DOCKER DEVELOPMENT ENVIRONMENT

Create Docker Compose configuration with:

1. frontend
2. backend
3. worker
4. scheduler
5. postgres
6. redis
7. n8n

Use named volumes for:

- PostgreSQL data.
- n8n configuration and workflow data.
- Temporary media shared between backend and worker.

Install FFmpeg and FFprobe in the appropriate backend/worker images.

Provide:

- Dockerfiles.
- docker-compose.yml.
- .env.example.
- Health checks.
- Startup dependencies.
- Database migrations.
- Development configuration.
- Production configuration.
- README setup instructions.

Ensure all services can start using:

docker compose up --build

Provide a clear local development URL for each service.

---

# 18. RELIABILITY AND MONITORING

Implement:

- Structured application logs.
- Workflow execution history.
- Provider request logs.
- Background job monitoring.
- Retry policies.
- Timeout policies.
- Idempotency keys.
- Health checks.
- Failure notifications.
- Recovery after restart.
- Safe cleanup.
- Duplicate-upload prevention.

Important:

Do not repeat paid generation requests simply because a callback or status response was delayed.

Before retrying, check whether the original external task is still active or already completed.

Make every workflow stage independently resumable.

---

# 19. TESTING

Create:

## Backend tests
- Song project APIs.
- Lyrics generation.
- Provider adapters.
- Music generation status.
- Video generation status.
- Rendering.
- Publishing.
- Cleanup.

## Frontend tests
- Dashboard.
- Song Studio.
- Lyrics editor.
- Music Studio.
- Video Studio.
- Publishing screens.

## Integration tests
- FastAPI and PostgreSQL.
- Celery and Redis.
- n8n webhooks.
- FFmpeg rendering.
- YouTube mock integration.

## Critical cleanup tests

Test that:

1. Failed music generation does not trigger cleanup.
2. Failed video generation does not trigger cleanup.
3. Failed rendering does not trigger cleanup.
4. Failed YouTube upload does not trigger cleanup.
5. Unverified YouTube processing does not trigger cleanup.
6. Successful verified publication triggers cleanup.
7. Repeated cleanup requests are safe.
8. Application restart does not cause accidental deletion.

---

# 20. IMPLEMENTATION PLAN

Do not attempt to implement the entire system in one operation.

Build it in verified phases.

## Phase 0: Architecture and API feasibility

Before coding:

1. Inspect repository.
2. Produce architecture documentation.
3. Produce database ER diagram.
4. Produce REST API specification.
5. Produce Docker service architecture.
6. Produce n8n workflow architecture.
7. Verify OpenAI API capabilities.
8. Verify official Suno API access and capabilities.
9. Verify Higgsfield API access and capabilities.
10. Verify Google OAuth and YouTube API requirements.
11. Document provider costs and access limitations.

Deliver:

- ARCHITECTURE.md
- IMPLEMENTATION_PLAN.md
- DATABASE_DESIGN.md
- API_SPECIFICATION.md
- PROVIDER_INTEGRATIONS.md
- N8N_WORKFLOWS.md
- SECURITY.md

Do not invent missing API details.

## Phase 1: Infrastructure

Build:

- React application.
- FastAPI application.
- PostgreSQL.
- Redis.
- Celery worker.
- Scheduler.
- n8n.
- Docker Compose.
- Health checks.

Verify every service starts successfully.

## Phase 2: Core application

Build:

- Database schema.
- Migrations.
- Song project CRUD.
- Dashboard.
- Song Studio.
- React-to-FastAPI integration.

## Phase 3: Autonomous content generation

Build:

- OpenAI integration.
- Telugu lyrics generation.
- Lyrics validation.
- Prompt templates.
- Music prompts.
- Visual prompts.
- YouTube metadata generation.

## Phase 4: Autonomous music generation

Build:

- Official Suno API adapter.
- Generation request handling.
- Asynchronous task tracking.
- Callback or polling.
- Audio retrieval.
- Audio validation.
- Candidate selection.
- Cost tracking.

Use manual audio upload only as an emergency fallback.

## Phase 5: Autonomous visual generation

Build:

- Higgsfield adapter.
- Video-generation prompts.
- Asynchronous generation.
- Status tracking.
- Video retrieval.
- Validation.
- Manual visual upload fallback.

## Phase 6: Video rendering

Build:

- FFmpeg rendering service.
- Video looping.
- Audio combination.
- Logo overlay.
- Thumbnail composition.
- Rendering progress.
- Preview.
- Retry.

## Phase 7: YouTube publishing

Build:

- Google OAuth.
- YouTube upload.
- Metadata.
- Thumbnails.
- Playlists.
- Scheduling.
- Publication verification.
- Cleanup.

## Phase 8: n8n automation

Create and test the complete production workflows.

Integrate every stage through authenticated FastAPI APIs.

Implement retries, approval gates and recovery.

## Phase 9: Analytics and optimization

Build YouTube analytics, performance reporting and cost monitoring.

---

# 21. IMPORTANT DEVELOPMENT RULES FOR CURSOR

Follow these rules throughout development:

1. First inspect the repository and existing files.
2. Do not overwrite existing user code without inspection.
3. Do not generate the entire application in one giant code-generation operation.
4. Implement only the currently approved phase.
5. Maintain clean architecture and separation of concerns.
6. Use TypeScript strictly.
7. Use Python type hints.
8. Avoid unnecessary dependencies.
9. Use environment configuration.
10. Do not hardcode credentials.
11. Do not invent third-party API functionality.
12. Do not use unofficial integrations.
13. Do not duplicate application logic in n8n.
14. Do not use cloud object storage.
15. Do not permanently retain generated media.
16. Do not delete media before verified publication.
17. Do not make the frontend responsible for background processing.
18. Make all expensive jobs asynchronous.
19. Keep workflow stages independently retryable.
20. Document every integration and environment variable.

After every phase:

- Run the application.
- Run tests.
- Fix errors.
- Verify Docker services.
- Update documentation.
- Provide a summary of completed features.
- Identify outstanding tasks.
- Wait for approval before proceeding to the next phase.

---

# 22. INITIAL TASK

Start by inspecting the repository.

Do not immediately generate the entire application.

First complete Phase 0 only.

Produce the architecture and implementation documents.

Pay special attention to:

- Official Suno API availability and autonomous music-generation capability.
- Higgsfield API availability and generation capability.
- YouTube API quotas and publishing constraints.
- Local storage and cleanup safety.
- n8n/Celery responsibilities.
- Estimated per-song generation costs.

Clearly distinguish:

- Confirmed API capabilities.
- Account-dependent capabilities.
- Features requiring manual fallback.
- Features that cannot currently be automated.

After Phase 0, show me the proposed architecture and implementation plan.

Wait for approval before implementing Phase 1.

# FINAL PRODUCT GOAL

Deliver a fully autonomous Telugu devotional YouTube production platform.

The user should be able to start a song project and let the system:

Generate lyrics
    -> Generate music
    -> Generate devotional visual
    -> Generate thumbnail
    -> Render complete video
    -> Generate YouTube metadata
    -> Upload video
    -> Schedule publication
    -> Verify publication
    -> Delete temporary local media

The normal workflow should require minimal manual intervention.

Keep approval gates configurable. The platform should support both supervised publishing and fully autonomous publishing once the user enables it.

Prioritize reliability, creative quality, cost control, Telugu language accuracy, maintainability and genuine content variation.