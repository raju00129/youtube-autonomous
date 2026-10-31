from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.workers.tasks import smoke_ping

router = APIRouter()


class SmokeRequest(BaseModel):
    message: str = Field(default="pong", max_length=200)


@router.post("/jobs/smoke")
def enqueue_smoke(body: SmokeRequest) -> dict:
    async_result = smoke_ping.delay(body.message)
    return {"data": {"job_id": async_result.id, "status": "queued", "job_type": "smoke"}}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    # AsyncResult works for any Celery task id (smoke, music, visuals)
    result = smoke_ping.AsyncResult(job_id)
    status = (result.status or "unknown").lower()
    payload: dict = {
        "job_id": job_id,
        "status": status,
    }
    info = result.info
    if isinstance(info, dict):
        # PROGRESS meta: {percent, message, ...}; also expose on STARTED
        payload["progress"] = {
            "percent": int(info.get("percent") or 0),
            "message": str(info.get("message") or ""),
            **{k: v for k, v in info.items() if k not in {"percent", "message"}},
        }
    if result.successful():
        payload["status"] = "success"
        payload["result"] = result.result
        if not payload.get("progress"):
            payload["progress"] = {"percent": 100, "message": "Done"}
    elif result.failed():
        err = result.result
        detail = str(err) if err is not None else "Job failed"
        if isinstance(info, Exception):
            detail = str(info)
        raise HTTPException(
            status_code=500,
            detail={"job_id": job_id, "status": "failure", "error": detail},
        )
    return {"data": payload}
