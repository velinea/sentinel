import asyncio
import base64
import hmac
import json
import logging
import tempfile
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
)
from starlette.background import BackgroundTask

from sentinel.config import load_config
from sentinel.nvr import NvrClient, NvrError, type_name

logger = logging.getLogger("sentinel.web")

config = load_config()
storage = Path(config.storage.path)
clips_path = Path(config.clips.save_path)
status_path = storage / "status.json"

app = FastAPI()

_NVR_CLIENT: NvrClient | None = None
if config.nvr:
    _NVR_CLIENT = NvrClient(
        host=config.nvr.host,
        user=config.nvr.user,
        password=config.nvr.password,
        http_port=config.nvr.http_port,
    )

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
<h1>Sentinel <a href="/live" style="font-size:0.8rem;color:#5b9;text-decoration:none;margin-left:0.75rem;vertical-align:middle;">Live &rsaquo;</a>{recordings_link}</h1>
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
        INDEX_HTML.replace(
            "{cards}", "\n".join(cards)
        ).replace(
            "{recordings_link}",
            ' <a href="/recordings" style="font-size:0.8rem;color:#5b9;'
            'text-decoration:none;margin-left:0.75rem;vertical-align:middle;">'
            "Recordings &rsaquo;</a>"
            if config.nvr
            else "",
        )
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


def _live_go2rtc_url(camera) -> str | None:
    link_base = (
        camera.go2rtc_stream_url
        or camera.go2rtc_url
        or (config.go2rtc.stream_url if config.go2rtc else None)
        or (config.go2rtc.url if config.go2rtc else None)
    )
    return link_base.rstrip("/") if link_base else None


@app.get("/live")
def live(_auth: None = Depends(_check_auth)):
    all_main = [
        camera
        for camera in config.cameras
        if camera.go2rtc_save_src and _live_go2rtc_url(camera)
    ]

    wanted = config.web.live_cameras
    if wanted:
        by_name = {camera.name: camera for camera in all_main}
        grid_cams = [
            by_name[name] for name in wanted if name in by_name
        ]
    else:
        grid_cams = all_main

    if not grid_cams:
        return HTMLResponse(
            "<p>No cameras with a main stream configured.</p>"
        )

    iframes = []
    for camera in grid_cams:
        base = _live_go2rtc_url(camera)
        url = f"{base}/stream.html?src={camera.go2rtc_save_src}"
        iframes.append(
            f'<iframe src="{url}" allow="autoplay" '
            f'title="{camera.name}"></iframe>'
        )

    return HTMLResponse(
        LIVE_HTML.replace("{iframes}", "\n".join(iframes))
    )


LIVE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinel &middot; Live</title>
<style>
  html, body { margin: 0; padding: 0; height: 100%; background: #000; overflow: hidden; }
  #grid { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr;
           height: 100vh; gap: 2px; }
  #grid iframe { width: 100%; height: 100%; border: none; }
  #back { position: fixed; top: 4px; right: 8px; color: rgba(255,255,255,0.35);
          text-decoration: none; font-size: 0.7rem; z-index: 10; }
</style>
</head>
<body>
<a id="back" href="/">Sentinel</a>
<div id="grid">
{iframes}
</div>
</body>
</html>
"""


def _nvr_or_404() -> NvrClient:
    if _NVR_CLIENT is None:
        raise HTTPException(
            status_code=503,
            detail="NVR not configured (set 'nvr' in config.yaml)",
        )
    return _NVR_CLIENT


def _nvr_cameras() -> list:
    return [
        camera
        for camera in config.cameras
        if camera.nvr_channel is not None
    ]


@app.get("/recordings")
def recordings_page(_auth: None = Depends(_check_auth)):
    cams = "".join(
        f'<option value="{camera.name}">{camera.name}</option>'
        for camera in _nvr_cameras()
    )
    if not cams:
        return HTMLResponse(
            "<p>No cameras have an NVR channel configured. Set "
            "`nvr_channel` on cameras in config.yaml.</p>"
        )
    return HTMLResponse(
        RECORDINGS_HTML.replace(
            "{camera_options}", cams
        ).replace("{cams_json}", "")
    )


@app.get("/recordings/search")
def recordings_search(
    date: str,
    camera: str,
    types: int = 15,
    _auth: None = Depends(_check_auth),
):
    client = _nvr_or_404()

    by_name = {cam.name: cam for cam in _nvr_cameras()}
    cam = by_name.get(camera)
    if cam is None:
        raise HTTPException(status_code=404, detail="Unknown camera")

    channel_mask = 1 << (cam.nvr_channel - 1)

    try:
        segments = client.search(
            date=date,
            channels=channel_mask,
            types=types,
        )
    except NvrError as exc:
        return {"error": str(exc)}

    rows = []
    now = time.time()
    for seg in segments:
        rows.append(
            {
                "channel": seg.channel,
                "type": seg.type,
                "type_name": type_name(seg.type),
                "begin": seg.begin,
                "end": seg.end,
                "duration": seg.end - seg.begin,
                "complete": seg.end <= now,
            }
        )

    return {"camera": camera, "segments": rows}


@app.get("/recordings/download")
async def recordings_download(
    channel: int,
    begin: int,
    end: int,
    _auth: None = Depends(_check_auth),
):
    client = _nvr_or_404()

    if channel < 0 or channel > 3:
        raise HTTPException(status_code=400, detail="Invalid channel (0-3)")

    tmpdir = Path(tempfile.mkdtemp(prefix="nvr_dl_"))

    def _cleanup():
        for p in tmpdir.iterdir():
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            tmpdir.rmdir()
        except OSError:
            pass

    try:
        flv_path = tmpdir / f"seg_{channel}_{begin}_{end}.flv"

        # Stream FLV to disk off the event loop (blocking httpx in a thread).
        await asyncio.to_thread(
            client.fetch_flv_to_path,
            channel,
            begin,
            end,
            str(flv_path),
        )

        mp4_path = flv_path.with_suffix(".mp4")

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(flv_path),
            "-c", "copy",
            "-movflags", "+faststart",
            "-f", "mp4",
            str(mp4_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0 or not mp4_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"FFmpeg remux failed (exit={proc.returncode}): "
                + stderr.decode(errors="replace")[-500:],
            )
    except NvrError as exc:
        # Free the large temp files immediately on failure.
        _cleanup()
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        _cleanup()
        raise

    return FileResponse(
        mp4_path,
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": (
                f"attachment; filename=\"nvr_ch{channel}_{begin}.mp4\""
            ),
        },
        background=BackgroundTask(_cleanup),
    )


RECORDINGS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinel &middot; NVR Recordings</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #111; color: #ddd;
         padding: 1.25rem; }
  h1 { font-size: 1.2rem; font-weight: 600; margin-bottom: 1rem; color: #fff; }
  h1 a { color: #5b9; text-decoration: none; font-size: 0.8rem; margin-left: 0.75rem;
         vertical-align: middle; }
  .controls { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap;
              margin-bottom: 1rem; }
  .controls label { font-size: 0.8rem; color: #999; }
  .controls input, .controls select { background: #2a2a2a; color: #fff;
           border: 1px solid #444; border-radius: 6px; padding: 0.4rem 0.5rem;
           font-size: 0.8rem; color-scheme: dark; }
  .controls input[type="date"] {
           background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23cfcfcf' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='4' width='18' height='18' rx='2' ry='2'/><line x1='16' y1='2' x2='16' y2='6'/><line x1='8' y1='2' x2='8' y2='6'/><line x1='3' y1='10' x2='21' y2='10'/></svg>");
           background-repeat: no-repeat; background-position: right 0.5rem center;
           padding-right: 2rem; cursor: pointer; }
  .controls input[type="date"]::-webkit-calendar-picker-indicator {
           opacity: 0; }
  .controls button { background: #2a5; color: #fff; border: none; border-radius: 6px;
           padding: 0.4rem 0.9rem; font-size: 0.8rem; cursor: pointer; }
  .controls button:disabled { background: #444; cursor: default; }
  .controls button.secondary { background: transparent; color: #5b9; border: 1px solid #333; }
  table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  th { text-align: left; color: #999; font-weight: 500; padding: 0.4rem 0.6rem;
       border-bottom: 1px solid #2a2a2a; }
  td { padding: 0.4rem 0.6rem; border-bottom: 1px solid #1d1d1d; }
  tr.still-recording td { color: #5b9; font-style: italic; }
  tr.missing td { color: #555; }
  a { color: #5b9; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .muted { color: #555; }
  .empty { color: #555; padding: 2rem 0; text-align: center; }
  .error { color: #e44; padding: 1rem 0; }
  .types-group { display: flex; gap: 0.4rem; margin-left: 0.5rem; }
  .types-group label { display: flex; align-items: center; gap: 0.2rem; cursor: pointer; }
</style>
</head>
<body>
<h1>NVR Recordings
  <a href="/">&laquo; Sentinel</a>
  <a href="/live" style="margin-left:0.4rem;">Live &rsaquo;</a>
</h1>

<div class="controls">
  <label>Date</label>
  <input type="date" id="date">
  <label>Camera</label>
  <select id="cam">{camera_options}</select>
  <label>Types</label>
  <div class="types-group">
    <label><input type="checkbox" name="type" value="1" checked>Time</label>
    <label><input type="checkbox" name="type" value="2" checked>Motion</label>
    <label><input type="checkbox" name="type" value="4" checked>Alarm</label>
  </div>
  <button id="btn-search" onclick="doSearch()">Search</button>
  <button class="secondary" id="btn-today" onclick="setToday()">Today</button>
</div>

<div id="results"></div>

<script>
(function () {
  var d = document.getElementById('date');
  var now = new Date();
  var mm = ('0' + (now.getMonth() + 1)).slice(-2);
  var dd = ('0' + now.getDate()).slice(-2);
  d.value = now.getFullYear() + '-' + mm + '-' + dd;
})();

function setToday() {
  var now = new Date();
  var mm = ('0' + (now.getMonth() + 1)).slice(-2);
  var dd = ('0' + now.getDate()).slice(-2);
  document.getElementById('date').value = now.getFullYear() + '-' + mm + '-' + dd;
  doSearch();
}

function tsStr(ts) {
  var d = new Date(ts * 1000);
  var hh = ('0' + d.getHours()).slice(-2);
  var mm = ('0' + d.getMinutes()).slice(-2);
  var ss = ('0' + d.getSeconds()).slice(-2);
  return hh + ':' + mm + ':' + ss;
}

function durStr(secs) {
  if (secs < 60) return secs + 's';
  var m = Math.floor(secs / 60);
  var s = secs % 60;
  return m + 'm ' + (s ? s + 's' : '');
}

function doSearch() {
  var btn = document.getElementById('btn-search');
  btn.disabled = true;
  var cam = document.getElementById('cam').value;
  var date = document.getElementById('date').value;
  var typeChecks = document.querySelectorAll('input[name="type"]:checked');
  var types = 0;
  for (var i = 0; i < typeChecks.length; i++) {
    types += parseInt(typeChecks[i].value);
  }
  if (!types) {
    document.getElementById('results').innerHTML = '<div class="error">Select at least one type</div>';
    btn.disabled = false;
    return;
  }

  var url = '/recordings/search?date=' + encodeURIComponent(date)
    + '&camera=' + encodeURIComponent(cam) + '&types=' + types;

  var controller = (window.AbortController) ? new AbortController() : null;
  var timer = (controller) ? setTimeout(function () { controller.abort(); }, 20000) : null;

  fetch(url, controller ? { signal: controller.signal } : {})
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.error) {
        document.getElementById('results').innerHTML = '<div class="error">' + data.error + '</div>';
        btn.disabled = false;
        return;
      }
      renderTable(data.segments, cam);
      btn.disabled = false;
    })
    .catch(function (err) {
      var msg = (err && err.name === 'AbortError') ? 'Request timed out' : ('Failed: ' + err);
      document.getElementById('results').innerHTML = '<div class="error">' + msg + '</div>';
      btn.disabled = false;
    })
    .finally(function () { if (timer) clearTimeout(timer); });
}

function renderTable(segs, cam) {
  if (!segs || !segs.length) {
    document.getElementById('results').innerHTML = '<div class="empty">No recordings found</div>';
    return;
  }
  var now = Math.floor(Date.now() / 1000);
  var html = '<table><thead><tr><th>Start</th><th>End</th><th>Duration</th><th>Type</th><th></th></tr></thead><tbody>';
  for (var i = 0; i < segs.length; i++) {
    var s = segs[i];
    var cls = '';
    var action = '';
    if (!s.complete) {
      cls = ' class="still-recording"';
      action = '<em>recording&hellip;</em>';
    } else {
      action = '<a href="/recordings/download?channel=' + s.channel
        + '&begin=' + s.begin + '&end=' + s.end + '">Download MP4</a>';
    }
    html += '<tr' + cls + '>'
      + '<td>' + tsStr(s.begin) + '</td>'
      + '<td>' + tsStr(s.end) + '</td>'
      + '<td>' + durStr(s.duration) + '</td>'
      + '<td>' + s.type_name + '</td>'
      + '<td>' + action + '</td>'
      + '</tr>';
  }
  html += '</tbody></table>';
  document.getElementById('results').innerHTML = html;
}
</script>
</body>
</html>
"""
