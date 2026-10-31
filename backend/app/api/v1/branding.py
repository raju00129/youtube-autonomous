"""Channel branding — logo used on every thumbnail."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import ChannelBrand

router = APIRouter(prefix="/branding", tags=["branding"])

ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def _get_or_create_brand(db: Session) -> ChannelBrand:
    brand = db.scalar(select(ChannelBrand).limit(1))
    if brand:
        return brand
    brand = ChannelBrand(channel_name="Ragam Spiritual")
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.get("")
def get_branding(db: Session = Depends(get_db)) -> dict:
    brand = _get_or_create_brand(db)
    return {
        "data": {
            "id": str(brand.id),
            "channel_name": brand.channel_name,
            "has_logo": bool(brand.logo_path),
            "logo_url": "/api/v1/branding/logo" if brand.logo_path else None,
            "logo_original_filename": brand.logo_original_filename,
            "thumbnail_layout": {
                "layers": [
                    "deity image / seasonal background",
                    "Telugu song title overlay",
                    "channel logo (corner brand mark)",
                ],
                "note": "Logo is composited locally during thumbnail generation — never baked into AI video clips.",
            },
        }
    }


@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    name = file.filename or "logo.png"
    suffix = Path(name).suffix.lower() or ".png"
    if suffix not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported logo type {suffix}")

    settings = get_settings()
    dest_dir = Path(settings.media_root) / "branding"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(name).stem)[:60] or "logo"
    dest = dest_dir / f"channel_logo_{uuid.uuid4().hex[:8]}{suffix}"
    data = await file.read()
    if len(data) > 10_000_000:
        raise HTTPException(status_code=413, detail="Logo too large")
    dest.write_bytes(data)

    brand = _get_or_create_brand(db)
    brand.logo_path = str(dest)
    brand.logo_original_filename = name
    db.commit()
    return get_branding(db)


@router.get("/logo")
def download_logo(db: Session = Depends(get_db)) -> FileResponse:
    brand = _get_or_create_brand(db)
    if not brand.logo_path:
        raise HTTPException(status_code=404, detail="No logo uploaded yet")
    path = Path(brand.logo_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Logo file missing")
    return FileResponse(path, filename=brand.logo_original_filename or path.name)
