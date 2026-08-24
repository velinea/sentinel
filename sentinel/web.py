import base64
import hmac
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    Response,
)

from sentinel.config import load_config

config = load_config()
storage = Path(config.storage.path)
clips_path = Path(config.clips.save_path)

app = FastAPI()

_AUTH_USER = config.web.auth_user
_AUTH_PASS = config.web.auth_password
_AUTH_ENABLED = bool(_AUTH_USER and _AUTH_PASS)


def _check_auth(request: Request) -> None:
    if not _AUTH_ENABLED:
        return

    auth = request.headers.get("Authorization", "")

    if not auth.startswith("Basic "):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="Sentinel"'},
        )

    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        user, password = decoded.split(":", 1)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="Sentinel"'},
        )

    user_ok = hmac.compare_digest(user, _AUTH_USER or "")
    pass_ok = hmac.compare_digest(password, _AUTH_PASS or "")

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="Sentinel"'},
        )


INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #111; color: #ddd; padding: 1.5rem; }
  h1 { font-size: 1.25rem; font-weight: 600; margin-bottom: 1.25rem; color: #fff; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }
  .card { background: #1a1a1a; border-radius: 8px; overflow: hidden; }
  .card-header { padding: 0.6rem 0.8rem; font-size: 0.85rem; font-weight: 500; color: #fff; border-bottom: 1px solid #2a2a2a; }
  .card-body { padding: 0.5rem; }
  .card-body img { width: 100%; border-radius: 4px; display: block; }
  .card-footer { padding: 0.5rem 0.8rem; border-top: 1px solid #2a2a2a; }
  .card-footer a { font-size: 0.8rem; color: #5b9; text-decoration: none; }
  .card-footer a:hover { text-decoration: underline; }
  .muted { color: #666; font-size: 0.8rem; }
</style>
</head>
<body>
<h1>Sentinel</h1>
<div class="grid">
{cards}
</div>
</body>
</html>
"""


def _build_index() -> HTMLResponse:
    cards = []

    for camera in config.cameras:
        name = camera.name
        objects = ", ".join(camera.objects)

        live_links = ""
        if camera.go2rtc_src:
            go2rtc_url = (
                camera.go2rtc_url
                or (config.go2rtc.url if config.go2rtc else None)
            )
            if go2rtc_url:
                if camera.go2rtc_url:
                    link_base = camera.go2rtc_url
                else:
                    link_base = (
                        (config.go2rtc.stream_url if config.go2rtc else None)
                        or go2rtc_url
                    )
                sub_url = (
                    f"{link_base}/stream.html"
                    f"?src={camera.go2rtc_src}"
                )
                live_links = f' <a href="{sub_url}" target="_blank">live (sub)</a>'
                if camera.go2rtc_save_src:
                    main_url = (
                        f"{link_base}/stream.html"
                        f"?src={camera.go2rtc_save_src}"
                    )
                    live_links += f' <a href="{main_url}" target="_blank">live (main)</a>'

        card = f"""\
<div class="card">
  <div class="card-header">{name}</div>
  <div class="card-body">
    <img src="/latest/{name}.jpg" alt="{name}" loading="lazy">
  </div>
  <div class="card-footer">
    <span class="muted">{objects}</span>
    &mdash;
    <a href="/latest/{name}.mp4">latest clip</a>{live_links}
  </div>
</div>"""
        cards.append(card)

    return HTMLResponse(
        INDEX_HTML.replace("{cards}", "\n".join(cards))
    )


@app.get("/")
def index(_auth: None = Depends(_check_auth)):
    return _build_index()


@app.get("/ping")
def ping():
    return PlainTextResponse("pong")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/latest/{camera}.jpg")
def latest_image(
    camera: str,
    _auth: None = Depends(_check_auth),
):
    image = storage / camera / "latest.jpg"

    if not image.exists():
        raise HTTPException(
            status_code=404,
            detail="No image available",
        )

    return FileResponse(
        image,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache",
        },
    )


@app.get("/latest/{camera}.mp4")
def latest_clip(
    camera: str,
    _auth: None = Depends(_check_auth),
):
    camera_dir = clips_path / camera

    if not camera_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="No clips available",
        )

    clips = sorted(
        camera_dir.glob("*.mp4"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not clips:
        raise HTTPException(
            status_code=404,
            detail="No clips available",
        )

    return FileResponse(
        clips[0],
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-cache",
        },
    )
