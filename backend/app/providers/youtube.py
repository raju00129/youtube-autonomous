"""YouTube Data API OAuth + channel helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.core.config import get_settings

logger = logging.getLogger(__name__)

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _token_path() -> Path:
    settings = get_settings()
    path = Path(settings.media_root) / "cache" / "youtube_oauth_token.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_token_raw() -> dict[str, Any] | None:
    path = _token_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write_token_raw(raw: dict[str, Any]) -> None:
    path = _token_path()
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def _expiry_from_raw(raw: dict[str, Any]) -> datetime | None:
    """Parse saved expiry; fall back from expires_in relative to saved_at."""
    exp = raw.get("expiry")
    if isinstance(exp, str) and exp.strip():
        try:
            dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    expires_in = raw.get("expires_in")
    saved_at = raw.get("saved_at")
    if expires_in and saved_at:
        try:
            base = datetime.fromisoformat(str(saved_at).replace("Z", "+00:00"))
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            return base + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            return None
    return None


def _persist_credentials(creds: Credentials, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write access + refresh tokens with absolute expiry so we can refresh later."""
    prev = previous or _read_token_raw() or {}
    refresh = creds.refresh_token or prev.get("refresh_token")
    expiry = creds.expiry
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    raw: dict[str, Any] = {
        **{k: v for k, v in prev.items() if k not in {"access_token", "refresh_token", "expiry", "saved_at"}},
        "token_type": "Bearer",
        "access_token": creds.token,
        "refresh_token": refresh,
        "scope": " ".join(creds.scopes or YOUTUBE_SCOPES),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    if expiry is not None:
        raw["expiry"] = expiry.astimezone(timezone.utc).isoformat()
        remaining = int((expiry.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds())
        raw["expires_in"] = max(remaining, 0)
    _write_token_raw(raw)
    return raw


def build_auth_url(state: str = "ragam") -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    previous = _read_token_raw() or {}
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        tokens = response.json()

    # Re-auth often omits refresh_token — keep the previous one.
    if not tokens.get("refresh_token") and previous.get("refresh_token"):
        tokens["refresh_token"] = previous["refresh_token"]

    now = datetime.now(timezone.utc)
    expires_in = int(tokens.get("expires_in") or 3600)
    tokens["saved_at"] = now.isoformat()
    tokens["expiry"] = (now + timedelta(seconds=expires_in)).isoformat()
    _write_token_raw(tokens)
    return tokens


def load_credentials(*, force_refresh: bool = False) -> Credentials | None:
    path = _token_path()
    if not path.exists():
        return None

    settings = get_settings()
    raw = _read_token_raw() or {}
    if not raw.get("refresh_token") and not raw.get("access_token"):
        return None

    expiry = _expiry_from_raw(raw)
    creds = Credentials(
        token=raw.get("access_token"),
        refresh_token=raw.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=YOUTUBE_SCOPES,
        expiry=expiry.replace(tzinfo=None) if expiry else None,  # google-auth uses naive UTC
    )

    # Missing expiry + refresh_token ⇒ assume stale (old bug) and refresh once.
    needs_refresh = bool(creds.refresh_token) and (
        force_refresh or creds.expired or expiry is None or not creds.token
    )
    if needs_refresh:
        try:
            creds.refresh(Request())
            _persist_credentials(creds, previous=raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("YouTube token refresh failed: %s", exc)
            if force_refresh or not creds.token:
                raise RuntimeError(
                    "YouTube session expired — reconnect via Connect YouTube"
                ) from exc
    return creds


def is_connected() -> bool:
    raw = _read_token_raw()
    return bool(raw and (raw.get("refresh_token") or raw.get("access_token")))


def fetch_mine_channel() -> dict[str, Any]:
    creds = load_credentials()
    if creds is None or not creds.token:
        raise RuntimeError("YouTube not connected. Visit /api/v1/youtube/auth first.")

    def _get(token: str) -> httpx.Response:
        with httpx.Client(timeout=30.0) as client:
            return client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "snippet,statistics,contentDetails", "mine": "true"},
                headers={"Authorization": f"Bearer {token}"},
            )

    response = _get(creds.token)
    if response.status_code == 401 and creds.refresh_token:
        creds = load_credentials(force_refresh=True)
        if creds is None or not creds.token:
            raise RuntimeError("YouTube not connected. Visit /api/v1/youtube/auth first.")
        response = _get(creds.token)
    response.raise_for_status()
    data = response.json()

    items = data.get("items") or []
    if not items:
        raise RuntimeError("No YouTube channel found for the authorized Google account.")

    channel = items[0]
    snippet = channel.get("snippet") or {}
    stats = channel.get("statistics") or {}
    settings = get_settings()
    return {
        "id": channel.get("id"),
        "title": snippet.get("title"),
        "custom_url": snippet.get("customUrl"),
        "description": snippet.get("description"),
        "thumbnail": (snippet.get("thumbnails") or {}).get("default", {}).get("url"),
        "subscriber_count": stats.get("subscriberCount"),
        "video_count": stats.get("videoCount"),
        "view_count": stats.get("viewCount"),
        "configured_channel_id": settings.youtube_channel_id,
        "configured_handle": settings.youtube_channel_handle,
        "matches_configured": channel.get("id") == settings.youtube_channel_id
        if settings.youtube_channel_id
        else None,
        "connected": True,
    }


def connection_status() -> dict[str, Any]:
    settings = get_settings()
    connected = is_connected()
    payload: dict[str, Any] = {
        "oauth_client_configured": bool(settings.google_client_id and settings.google_client_secret),
        "connected": connected,
        "configured_channel": {
            "id": settings.youtube_channel_id,
            "handle": settings.youtube_channel_handle,
            "url": settings.youtube_channel_url,
        },
        "auth_url": build_auth_url() if settings.google_client_id else None,
    }
    if connected:
        try:
            payload["channel"] = fetch_mine_channel()
        except Exception as exc:  # noqa: BLE001 — surface status without crashing
            payload["channel_error"] = str(exc)
    return payload


def list_playlists(max_results: int = 50) -> list[dict[str, str]]:
    """List playlists for the authorized channel."""
    creds = load_credentials()
    if creds is None or not creds.token:
        raise RuntimeError("YouTube not connected. Visit /api/v1/youtube/auth first.")

    items: list[dict[str, str]] = []
    page_token: str | None = None
    refreshed = False
    with httpx.Client(timeout=30.0) as client:
        while True:
            params: dict[str, Any] = {
                "part": "snippet,contentDetails",
                "mine": "true",
                "maxResults": min(50, max_results - len(items)),
            }
            if page_token:
                params["pageToken"] = page_token
            response = client.get(
                "https://www.googleapis.com/youtube/v3/playlists",
                params=params,
                headers={"Authorization": f"Bearer {creds.token}"},
            )
            if response.status_code == 401 and creds.refresh_token and not refreshed:
                creds = load_credentials(force_refresh=True)
                if creds is None or not creds.token:
                    raise RuntimeError("YouTube not connected. Visit /api/v1/youtube/auth first.")
                refreshed = True
                continue
            response.raise_for_status()
            data = response.json()
            for row in data.get("items") or []:
                snippet = row.get("snippet") or {}
                items.append(
                    {
                        "id": row.get("id") or "",
                        "title": snippet.get("title") or "",
                        "item_count": str(
                            (row.get("contentDetails") or {}).get("itemCount", "")
                        ),
                    }
                )
            page_token = data.get("nextPageToken")
            if not page_token or len(items) >= max_results:
                break
    return items


class YouTubeUploadError(RuntimeError):
    pass


def _yt_service():
    from googleapiclient.discovery import build

    creds = load_credentials()
    if creds is None or not creds.token:
        raise YouTubeUploadError("YouTube not connected. Visit /api/v1/youtube/auth first.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    tags: list[str] = []
    for part in raw.replace("\n", ",").split(","):
        t = part.strip().lstrip("#")
        if t and t not in tags:
            tags.append(t[:30])
        if len(tags) >= 15:
            break
    return tags


def upload_video(
    *,
    file_path: str | Path,
    title: str,
    description: str = "",
    tags: str | list[str] | None = None,
    category_id: str = "10",
    privacy_status: str = "public",
    publish_at: str | None = None,
    made_for_kids: bool = False,
    contains_synthetic_media: bool | None = None,
) -> dict[str, Any]:
    """Resumable upload. Returns {video_id, url, raw}."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    path = Path(file_path)
    if not path.exists():
        raise YouTubeUploadError(f"Video file missing: {path}")

    tag_list = _parse_tags(tags) if isinstance(tags, str) or tags is None else list(tags)
    privacy = (privacy_status or "public").strip().lower()
    if privacy not in {"public", "unlisted", "private"}:
        privacy = "public"

    if contains_synthetic_media is None:
        contains_synthetic_media = bool(
            getattr(get_settings(), "youtube_contains_synthetic_media", True)
        )
    status: dict[str, Any] = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": bool(made_for_kids),
        # YouTube "Altered or synthetic content" disclosure (AI music/visuals)
        "containsSyntheticMedia": bool(contains_synthetic_media),
    }
    # Scheduling requires private + publishAt (RFC 3339)
    if publish_at and privacy == "private":
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": (title or "Ragam Spiritual Telugu")[:100],
            "description": (description or "")[:4900],
            "tags": tag_list,
            "categoryId": category_id,
        },
        "status": status,
    }

    youtube = _yt_service()
    media = MediaFileUpload(
        str(path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=8 * 1024 * 1024,
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    try:
        while response is None:
            _status, response = request.next_chunk()
    except HttpError as exc:
        raise YouTubeUploadError(f"YouTube upload failed: {exc}") from exc

    video_id = (response or {}).get("id")
    if not video_id:
        raise YouTubeUploadError(f"YouTube upload returned no video id: {response}")
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "raw": response,
    }


def set_thumbnail(*, video_id: str, image_path: str | Path) -> dict[str, Any]:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    path = Path(image_path)
    if not path.exists():
        raise YouTubeUploadError(f"Thumbnail missing: {path}")
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    youtube = _yt_service()
    try:
        return (
            youtube.thumbnails()
            .set(videoId=video_id, media_body=MediaFileUpload(str(path), mimetype=mime))
            .execute()
        )
    except HttpError as exc:
        raise YouTubeUploadError(f"Thumbnail set failed: {exc}") from exc


def add_to_playlist(*, playlist_id: str, video_id: str) -> dict[str, Any]:
    from googleapiclient.errors import HttpError

    if not playlist_id or not video_id:
        raise YouTubeUploadError("playlist_id and video_id required")
    youtube = _yt_service()
    try:
        return (
            youtube.playlistItems()
            .insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                },
            )
            .execute()
        )
    except HttpError as exc:
        # 409 / already exists — treat as success-ish
        msg = str(exc)
        if "duplicate" in msg.lower() or getattr(exc, "resp", None) and exc.resp.status == 409:
            return {"status": "already_in_playlist", "playlist_id": playlist_id, "video_id": video_id}
        raise YouTubeUploadError(f"Add to playlist failed: {exc}") from exc


def update_video_snippet(
    *,
    video_id: str,
    title: str,
    description: str,
    tags: str | list[str] | None = None,
    category_id: str = "10",
) -> dict[str, Any]:
    """Update title/description/tags (used to pin Short → long-form link)."""
    from googleapiclient.errors import HttpError

    if not video_id:
        raise YouTubeUploadError("video_id required")
    tag_list = _parse_tags(tags) if isinstance(tags, str) or tags is None else list(tags)
    youtube = _yt_service()
    body = {
        "id": video_id,
        "snippet": {
            "title": (title or "Ragam Spiritual Telugu")[:100],
            "description": (description or "")[:4900],
            "tags": tag_list,
            "categoryId": category_id,
        },
    }
    try:
        return youtube.videos().update(part="snippet", body=body).execute()
    except HttpError as exc:
        raise YouTubeUploadError(f"Video metadata update failed: {exc}") from exc


def set_synthetic_media_flag(*, video_id: str, value: bool = True) -> dict[str, Any]:
    """Set the A/S disclosure on an existing video, keeping its other status fields.

    videos.update(part=status) replaces the whole status object, so the current
    writable fields are read back and re-sent unchanged.
    """
    from googleapiclient.errors import HttpError

    if not video_id:
        raise YouTubeUploadError("video_id required")
    youtube = _yt_service()
    try:
        items = youtube.videos().list(part="status", id=video_id).execute().get("items") or []
        if not items:
            raise YouTubeUploadError(f"Video not found: {video_id}")
        current = items[0].get("status") or {}
        if bool(current.get("containsSyntheticMedia")) == bool(value):
            return {"video_id": video_id, "changed": False}
        status: dict[str, Any] = {
            k: current[k]
            for k in (
                "privacyStatus",
                "embeddable",
                "license",
                "publicStatsViewable",
                "selfDeclaredMadeForKids",
            )
            if k in current
        }
        if current.get("privacyStatus") == "private" and current.get("publishAt"):
            status["publishAt"] = current["publishAt"]
        status["containsSyntheticMedia"] = bool(value)
        youtube.videos().update(part="status", body={"id": video_id, "status": status}).execute()
        return {"video_id": video_id, "changed": True}
    except HttpError as exc:
        raise YouTubeUploadError(f"Synthetic-media flag update failed: {exc}") from exc


def short_related_description(
    *,
    base_description: str,
    main_video_id: str,
    main_url: str | None = None,
) -> str:
    """Put the long-form watch link at the top so Shorts point at the right full song."""
    watch = (main_url or "").strip() or f"https://www.youtube.com/watch?v={main_video_id}"
    short_link = f"https://youtu.be/{main_video_id}"
    header = (
        f"▶ Full song (related video): {watch}\n"
        f"▶ {short_link}\n\n"
    )
    body = (base_description or "").strip()
    # Drop stale placeholders / duplicate full-song lines
    cleaned_lines: list[str] = []
    for line in body.splitlines():
        low = line.lower().strip()
        if "full song" in low and ("link added" in low or "our channel" in low):
            continue
        if main_video_id and main_video_id in line:
            continue
        if "youtu.be/" in low or "youtube.com/watch" in low:
            continue
        cleaned_lines.append(line)
    body = "\n".join(cleaned_lines).strip()
    return f"{header}{body}"[:4900]
