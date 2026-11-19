from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.channels import ChannelKey, channel_key_dependency, get_channel, normalize_channel_key
from app.providers import youtube as yt

router = APIRouter(prefix="/youtube")


@router.get("/status")
def youtube_status(
    channel_key: ChannelKey = Depends(channel_key_dependency),
) -> dict:
    return {"data": yt.connection_status(channel_key)}


@router.get("/channels")
def youtube_channels() -> dict:
    """List Telugu + Hindi channel profiles and connect URLs."""
    return {"data": {"channels": yt.connection_status("te").get("channels") or []}}


@router.get("/auth")
def youtube_auth(
    channel_key: str | None = Query(default=None),
    x_channel_key: str | None = Header(default=None, alias="X-Channel-Key"),
) -> RedirectResponse:
    # Prefer ?channel_key= (browser <a> clicks send no X-Channel-Key).
    # Missing query used to default to te — Hindi Connect then overwrote/never created hi token.
    ck = normalize_channel_key(channel_key or x_channel_key)
    status = yt.connection_status(ck)
    if not status["oauth_client_configured"]:
        raise HTTPException(status_code=500, detail="Google OAuth client is not configured")
    return RedirectResponse(url=status["auth_url"])


@router.get("/callback")
def youtube_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
) -> HTMLResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    ck = normalize_channel_key(state)
    profile = get_channel(ck)
    try:
        yt.exchange_code(code, channel_key=ck)
        channel = yt.fetch_mine_channel(ck)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    match_note = ""
    if channel.get("matches_configured") is False:
        match_note = (
            "<p style='color:#c45c26'>Authorized channel ID does not match configured "
            f"<code>{channel.get('configured_channel_id')}</code> for "
            f"<strong>{profile.display_name}</strong> ({ck}). "
            "In Google's channel picker, select the correct YouTube channel, then reconnect.</p>"
        )
    elif channel.get("matches_configured") is True:
        match_note = (
            f"<p style='color:#2f4a3c'>Authorized channel matches configured "
            f"<strong>{profile.display_name}</strong> ({ck}).</p>"
        )

    other = "te" if ck == "hi" else "hi"
    other_profile = get_channel(other)
    html = f"""
    <html><body style="font-family:system-ui;padding:2rem;background:#f7f1e8;color:#1a1410">
      <h1>YouTube connected — {profile.display_name}</h1>
      <p>Studio channel key: <code>{ck}</code> · language <code>{profile.language}</code></p>
      <p><strong>{channel.get('title')}</strong></p>
      <p>Channel ID: <code>{channel.get('id')}</code></p>
      <p>Handle: <code>{channel.get('custom_url') or channel.get('configured_handle')}</code></p>
      {match_note}
      <p>Telugu and Hindi each need their own Connect. This token is only for
         <strong>{ck}</strong>. To connect the other channel, switch the studio
         toggle to {other_profile.display_name} and click Connect again
         (<a href="/api/v1/youtube/auth?channel_key={other}">connect {other}</a>).</p>
      <p><a href="/">Back to studio</a> ·
         <a href="/api/v1/youtube/channel?channel_key={ck}">API channel JSON</a></p>
    </body></html>
    """
    return HTMLResponse(content=html)


@router.get("/channel")
def youtube_channel(
    channel_key: ChannelKey = Depends(channel_key_dependency),
) -> dict:
    try:
        return {"data": yt.fetch_mine_channel(channel_key)}
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
