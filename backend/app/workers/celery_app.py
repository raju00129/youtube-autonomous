from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ragam",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule={
        # Scan for songs needing video+mix (~1h before publish) or YouTube upload
        "pipeline-tick-every-5-minutes": {
            "task": "app.workers.tasks.pipeline_tick",
            "schedule": 300.0,  # seconds
            "options": {"expires": 240},
        },
    },
)
