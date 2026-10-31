from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.providers import youtube as yt

router = APIRouter(prefix="/youtube")


@router.get("/status")
def youtube_status() -> dict:
    return {"data": yt.connection_status()}


@router.get("/auth")
def youtube_auth() -> RedirectResponse:
    status = yt.connection_status()
    if not status["oauth_client_configured"]:
        raise HTTPException(status_code=500, detail="Google OAuth client is not configured")
    return RedirectResponse(url=status["auth_url"])


@router.get("/callback")
def youtube_callback(code: str | None = None, error: str | None = None, state: str | None = None) -> HTMLResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        yt.exchange_code(code)
        channel = yt.fetch_mine_channel()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    match_note = ""
    if channel.get("matches_configured") is False:
        match_note = (
            "<p style='color:#c45c26'>Authorized channel ID does not match configured "
            f"<code>{channel.get('configured_channel_id')}</code>. "
            "Sign in with the Google account that owns Ragam Spiritual Telugu.</p>"
        )
    elif channel.get("matches_configured") is True:
        match_note = "<p style='color:#2f4a3c'>Authorized channel matches configured Ragam Spiritual Telugu channel.</p>"

    html = f"""
    <html><body style="font-family:system-ui;padding:2rem;background:#f7f1e8;color:#1a1410">
      <h1>YouTube connected</h1>
      <p><strong>{channel.get('title')}</strong></p>
      <p>Channel ID: <code>{channel.get('id')}</code></p>
      <p>Handle: <code>{channel.get('custom_url') or channel.get('configured_handle')}</code></p>
      {match_note}
      <p><a href="http://localhost:5173">Back to dashboard</a> ·
         <a href="/api/v1/youtube/channel">API channel JSON</a></p>
    </body></html>
    """
    return HTMLResponse(content=html)


@router.get("/channel")
def youtube_channel() -> dict:
    try:
        return {"data": yt.fetch_mine_channel()}
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
