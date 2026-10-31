from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
def api_status() -> dict[str, str]:
    return {"api": "v1", "status": "ok"}
