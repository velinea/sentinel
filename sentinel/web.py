import base64
import hmac
import json
import time
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
status_path = storage / "status.json"

app = FastAPI()

_AUTH_USER = config.web.auth_user
_AUTH_PASS = config.web.auth_password
_AUTH_TOKEN = config.web.token
_AUTH_ENABLED = bool(
    (_AUTH_USER and _AUTH_PASS) or _AUTH_TOKEN
)
_COOKIE_NAME = "sentinel_token"
_COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def _auth_source(request: Request) -> str | None:
    """Return the auth source ("token", "cookie", "basic") or None."""
    token = request.query_params.get("token")
    if _AUTH_TOKEN and token:
        if hmac.compare_digest(token, _AUTH_TOKEN):
            return "token"

    cookie = request.cookies.get(_COOKIE_NAME)
    if _AUTH_TOKEN and cookie:
        if hmac.compare_digest(cookie, _AUTH_TOKEN):
            return "cookie"

    if _AUTH_USER and _AUTH_PASS:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode(
                    "utf-8"
                )
                user, password = decoded.split(":", 1)
            except Exception:
                return None

            if (
                hmac.compare_digest(user, _AUTH_USER)
                and hmac.compare_digest(
                    password, _AUTH_PASS
                )
            ):
                return "basic"

    return None


def _check_auth(request: Request) -> None:
    if not _AUTH_ENABLED:
        return

    source = _auth_source(request)

    if source is None:
        headers = {}
        if _AUTH_USER and _AUTH_PASS:
            headers = {
                "WWW-Authenticate": 'Basic realm="Sentinel"'
            }
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers=headers,
        )


@app.middleware("http")
async def remember_auth(request, call_next):
    response = await call_next(request)

    source = _auth_source(request)
    if _AUTH_TOKEN and source in ("token", "basic"):
        response.set_cookie(
            _COOKIE_NAME,
            _AUTH_TOKEN,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )

    return response


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
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 0.4rem; vertical-align: middle; }
  .dot-green { background: #4a4; }
  .dot-red { background: #e44; }
  .dot-gray { background: #555; }
  .error-text { color: #e44; font-size: 0.75rem; display: block; margin-top: 0.25rem; }
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
    status: dict = {}
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass

    cam_status_map = status.get("cameras", {})
    cards: list[str] = []

    for camera in config.cameras:
        name = camera.name
        objects = ", ".join(camera.objects)

        cam_status = cam_status_map.get(name, {})
        last_ok = cam_status.get("last_ok", 0.0)
        last_error = cam_status.get("last_error", 0.0)
        error_msg = cam_status.get("error", "")

        if error_msg and last_error > last_ok:
            dot = '<span class="dot dot-red"></span>'
            error_html = (
                f'<span class="error-text">{error_msg}</span>'
            )
        elif last_ok > 0:
            dot = '<span class="dot dot-green"></span>'
            error_html = ""
        else:
            dot = '<span class="dot dot-gray"></span>'
            error_html = ""

        live_links = ""
        if camera.go2rtc_src:
            go2rtc_url = (
                camera.go2rtc_url
                or (config.go2rtc.url if config.go2rtc else None)
            )
            if go2rtc_url:
                link_base = (
                    camera.go2rtc_stream_url
                    or (config.go2rtc.stream_url if config.go2rtc else None)
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

        img_v = ""
        latest_jpg = storage / name / "latest.jpg"
        if latest_jpg.is_file():
            img_v = f"?v={int(latest_jpg.stat().st_mtime)}"

        clip_v = ""
        camera_dir = clips_path / name
        if camera_dir.is_dir():
            newest = max(
                (
                    f
                    for f in camera_dir.glob("*.mp4")
                    if f.is_file()
                ),
                key=lambda f: f.stat().st_mtime,
                default=None,
            )
            if newest is not None:
                clip_v = f"?v={int(newest.stat().st_mtime)}"

        card = f"""\
<div class="card">
  <div class="card-header">{dot} {name}</div>
  <div class="card-body">
    <img src="/latest/{name}.jpg{img_v}" alt="{name}" loading="lazy">
  </div>
  <div class="card-footer">
    <span class="muted">{objects}</span>
    {error_html}
    &mdash;
    <a href="/latest/{name}.mp4{clip_v}">latest clip</a>{live_links}
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
            "Cache-Control": "no-store",
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
            "Cache-Control": "no-store",
        },
    )
