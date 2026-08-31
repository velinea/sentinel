"""Client for the XiongMai-style NVR CGI API.

The NVR exposes a proprietary XML-over-HTTP gateway at /cgi-bin/gw.cgi plus an
FLV download/stream endpoint at /cgi-bin/flv.cgi. There is no RTSP. Recorders
are H.264/AVC in FLV containers.

These NVRs allow multiple concurrent flv.cgi streams (verified), so requests
are NOT serialized behind a global lock -- a stuck download must not block
searches or other requests. A short-lived login check is cached and only
re-verified when a call reports an auth failure.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass

import httpx

logger = logging.getLogger("sentinel.nvr")

# Recording type bit flags used by recsearch
TYPE_TIME = 1
TYPE_MOTION = 2
TYPE_SENSOR = 4
TYPE_MANUAL = 8

ALL_TYPES = TYPE_TIME | TYPE_MOTION | TYPE_SENSOR | TYPE_MANUAL

_TYPE_NAMES = {
    TYPE_TIME: "Time",
    TYPE_MOTION: "Motion",
    TYPE_SENSOR: "Alarm",
    TYPE_MANUAL: "Manual",
}


class NvrError(Exception):
    """Raised for NVR communication or auth failures."""


@dataclass
class Segment:
    channel: int  # 0-indexed NVR channel, matching flv.cgi chn (0-3)
    type: int
    begin: int  # unix seconds
    end: int  # unix seconds


def type_name(t: int) -> str:
    return _TYPE_NAMES.get(t, str(t))


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


class NvrClient:
    def __init__(self, host: str, user: str, password: str, http_port: int = 80):
        self.host = host
        self.user = user
        self.password = password
        self.port = http_port
        self._base = f"http://{host}:{http_port}"
        self._auth_ok = False
        self._auth_lock = threading.Lock()

    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        try:
            response = httpx.get(
                f"{self._base}{path}",
                params=params,
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            detail = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                detail = f"{exc} NVR response: {exc.response.text[:200]!r}"
            raise NvrError(f"NVR request failed: {detail}") from exc
        return response

    def fetch_flv_to_path(
        self,
        channel: int,
        begin: int,
        end: int,
        dest: str,
        retries: int = 3,
    ) -> str:
        """Stream an FLV segment to `dest`, retrying transient failures.

        Returns the segment name (channel, begin). Runs without holding any
        lock so a slow/stuck download never blocks searches or other calls.
        """
        url = self._base + "/cgi-bin/flv.cgi?" + urllib.parse.urlencode(
            {
                "u": self.user,
                "p": self.password,
                "mode": "time",
                "chn": channel,
                "begin": begin,
                "end": end,
                "mute": "false",
                "download": "1",
            }
        )
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                with httpx.stream(
                    "GET",
                    url,
                    timeout=(5.0, 60.0),
                    follow_redirects=True,
                ) as response:
                    if response.status_code != 200:
                        body = response.read()[:200].decode(errors="replace")
                        raise NvrError(
                            f"NVR stream returned {response.status_code}: {body!r}"
                        )
                    with open(dest, "wb") as fh:
                        for chunk in response.iter_bytes(
                            chunk_size=1 << 20
                        ):
                            fh.write(chunk)
                return f"ch{channel}_{begin}"
            except (httpx.HTTPError, NvrError, OSError) as exc:
                last_exc = exc
                logger.warning(
                    "NVR stream fetch failed (attempt %d/%d) ch%s: %s",
                    attempt + 1,
                    retries,
                    channel,
                    exc,
                )
                if attempt < retries - 1:
                    time.sleep(2)
        raise NvrError(
            f"NVR segment download failed after {retries} attempts: {last_exc}"
        )

    def _ensure_auth(self) -> None:
        """Login-check once; only re-verify if auth previously failed."""
        if self._auth_ok:
            return
        xml = (
            '<juan ver="" squ="" dir="0">'
            f'<rpermission usr="{_xml_escape(self.user)}" '
            f'pwd="{_xml_escape(self.password)}">'
            "<config base=\"\" /><playback base=\"\" />"
            "</rpermission></juan>"
        )
        response = self._get("/cgi-bin/gw.cgi", {"xml": xml})
        match = re.search(
            r'<rpermission[^>]*errno="([^"]*)"[^>]*(remain="([^"]*)")?[^>]*'
            r'(locktime="([^"]*)")?',
            response.text,
        )
        errno = match.group(1) if match else None
        if errno == "0":
            with self._auth_lock:
                self._auth_ok = True
            return
        remain = match.group(3) if match else None
        locktime = match.group(5) if match else None
        if locktime and int(float(locktime)) > 0:
            raise NvrError(
                "NVR account is temporarily locked out "
                f"(unlocks in ~{int(float(locktime))}s)"
            )
        if errno == "4":
            raise NvrError("NVR login failed: incorrect username or password")
        raise NvrError(f"NVR login failed (errno={errno})")

    def _invalidate_auth(self) -> None:
        with self._auth_lock:
            self._auth_ok = False

    def search(
        self,
        date: str,
        channels: int,
        types: int = ALL_TYPES,
        begin: str = "0:0:0",
        end: str = "23:59:59",
        page_size: int = 200,
    ) -> list[Segment]:
        """Return continuous recording segments for the given day.

        `channels` is a bitmask (bit 0 = physical channel 1); flv.cgi channel
        numbers are 0-indexed, so `Segment.channel` is 0-indexed to match.
        `date` is YYYY-M-D. Segments are returned in reverse-chronological
        order as the NVR lists them.
        """
        self._ensure_auth()
        xml = (
            '<juan ver="0" squ="abcdef" dir="0" enc="1">'
            f'<recsearch usr="{_xml_escape(self.user)}" '
            f'pwd="{_xml_escape(self.password)}" '
            f'channels="{channels}" types="{types}" '
            f'date="{_xml_escape(date)}" '
            f'begin="{_xml_escape(begin)}" end="{_xml_escape(end)}" '
            'session_index="0" '
            f'session_count="{page_size}" '
            "/></juan>"
        )
        response = self._get("/cgi-bin/gw.cgi", {"xml": xml})
        text = response.text
        search_match = re.search(r"<recsearch[^>]*errno=\"([^\"]*)\"", text)
        errno = search_match.group(1) if search_match else None
        if errno != "0":
            raise NvrError(f"NVR search failed (errno={errno})")

        segments: list[Segment] = []
        for s in re.findall(r"<s>([^<]*)</s>", text):
            parts = s.split("|")
            if len(parts) < 6:
                continue
            try:
                channel_index = int(parts[2])
                seg_type = int(parts[3])
                begin_ts = int(parts[4])
                end_ts = int(parts[5])
            except ValueError:
                continue
            if end_ts <= begin_ts:
                continue
            segments.append(
                Segment(
                    channel=channel_index,
                    type=seg_type,
                    begin=begin_ts,
                    end=end_ts,
                )
            )
        return segments
