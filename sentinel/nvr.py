"""Client for the XiongMai-style NVR CGI API.

The NVR exposes a proprietary XML-over-HTTP gateway at /cgi-bin/gw.cgi plus an
FLV download/stream endpoint at /cgi-bin/flv.cgi. There is no RTSP. Recorders
are H.264/AVC in FLV containers.

These devices only allow a single active web/API session at a time, so every
call is serialized through a module-level lock.
"""

from __future__ import annotations

import logging
import re
import threading
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
    channel: int  # 1-indexed, matching flv.cgi
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
        self._lock = threading.Lock()

    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        with self._lock:
            try:
                response = httpx.get(
                    f"{self._base}{path}",
                    params=params,
                    timeout=20.0,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise NvrError(f"NVR request failed: {exc}") from exc
        return response

    @staticmethod
    def _parse_xml_attrs(xml: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for key, value in re.findall(r'([\w_]+)="([^"]*)"', xml):
            attrs[key] = urllib.parse.unquote(value)
        return attrs

    def _login(self) -> None:
        """Verify credentials. Raises NvrError if invalid/locked."""
        xml = (
            '<juan ver="" squ="" dir="0">'
            f'<rpermission usr="{_xml_escape(self.user)}" '
            f'pwd="{_xml_escape(self.password)}">'
            "<config base=\"\" /><playback base=\"\" />"
            "</rpermission></juan>"
        )
        response = self._get(
            "/cgi-bin/gw.cgi",
            {"xml": xml},
        )
        match = re.search(
            r'<rpermission[^>]*errno="([^"]*)"[^>]*(remain="([^"]*)")?[^>]*'
            r'(locktime="([^"]*)")?',
            response.text,
        )
        errno = match.group(1) if match else None
        if errno == "0":
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

        `channels` is a bitmask (bit 0 = physical channel 1). `date` is
        YYYY-M-D. Segments are returned in reverse-chronological order as the
        NVR lists them.
        """
        self._login()
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
        response = self._get(
            "/cgi-bin/gw.cgi",
            {"xml": xml},
        )
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
                    channel=channel_index + 1,
                    type=seg_type,
                    begin=begin_ts,
                    end=end_ts,
                )
            )
        return segments

    def stream_url(
        self,
        channel: int,
        begin: int,
        end: int,
        download: bool = True,
    ) -> str:
        """Build the flv.cgi URL for one channel/time range."""
        query = urllib.parse.urlencode(
            {
                "u": self.user,
                "p": self.password,
                "mode": "time",
                "chn": channel,
                "begin": begin,
                "end": end,
                "mute": "false",
                "download": "1" if download else "false",
            }
        )
        return f"{self._base}/cgi-bin/flv.cgi?{query}"

    def fetch_flv(self, channel: int, begin: int, end: int) -> httpx.Response:
        """Stream the raw FLV response for a segment (downloaded to memory)."""
        return self._get(
            "/cgi-bin/flv.cgi",
            {
                "u": self.user,
                "p": self.password,
                "mode": "time",
                "chn": channel,
                "begin": begin,
                "end": end,
                "mute": "false",
                "download": "1",
            },
        )
