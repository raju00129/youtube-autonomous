from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.middleware.portal_auth import COOKIE_NAME

router = APIRouter(prefix="/portal", tags=["portal"])


class UnlockBody(BaseModel):
    key: str = Field(min_length=1, max_length=64)


@router.post("/unlock")
def unlock_portal(body: UnlockBody, response: Response) -> dict[str, bool]:
    settings = get_settings()
    expected = (settings.portal_access_key or "").strip()
    if not expected or body.key.strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid access key")

    secure = settings.environment.strip().lower() == "production"
    response.set_cookie(
        key=COOKIE_NAME,
        value=expected,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return {"ok": True}
