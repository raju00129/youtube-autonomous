"""Set Telugu as video + audio language on every channel upload that is not already Telugu.

Auto captions are generated in the video's audio language, so Shorts left on
en-US were getting wrong (e.g. Kannada) auto subtitles.

Run inside the backend container:
    docker compose exec -T backend python - < scripts/fix_video_language.py
"""

from __future__ import annotations

from app.providers.youtube import YouTubeUploadError, _yt_service, set_video_language


def main() -> None:
    yt = _yt_service()
    uploads = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0][
        "contentDetails"
    ]["relatedPlaylists"]["uploads"]
    ids: list[str] = []
    token = None
    while True:
        page = (
            yt.playlistItems()
            .list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=token)
            .execute()
        )
        ids += [it["contentDetails"]["videoId"] for it in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            break

    changed = unchanged = failed = 0
    for i in range(0, len(ids), 50):
        batch = yt.videos().list(part="snippet", id=",".join(ids[i : i + 50])).execute()
        for video in batch.get("items", []):
            vid = video["id"]
            snippet = video.get("snippet") or {}
            try:
                if set_video_language(video_id=vid, snippet=snippet):
                    changed += 1
                    print(
                        "fixed",
                        vid,
                        snippet.get("defaultLanguage"),
                        snippet.get("defaultAudioLanguage"),
                        "-> te",
                    )
                else:
                    unchanged += 1
            except YouTubeUploadError as exc:
                failed += 1
                print("fail", vid, str(exc)[:160])
                if "quotaExceeded" in str(exc):
                    print(f"STOPPED on quota changed={changed} already={unchanged} failed={failed}")
                    return
    print(f"DONE changed={changed} already={unchanged} failed={failed}")


if __name__ == "__main__":
    main()
