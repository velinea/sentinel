import time
from typing import Protocol

import httpx

from sentinel.ha.client import HomeAssistantClient


class SnapshotSource(Protocol):
    def get_snapshot(self) -> bytes: ...


class HASource:
    def __init__(self, client: HomeAssistantClient, entity: str):
        self.client = client
        self.entity = entity

    def get_snapshot(self) -> bytes:
        return self.client.get_snapshot(self.entity)


class Go2rtcSource:
    def __init__(self, url: str, src: str):
        self.base_url = url
        self.src = src
        self._client = httpx.Client(
            base_url=url,
            timeout=10.0,
        )

    def get_snapshot(self) -> bytes:
        response = self._client.get(
            "/api/frame.jpeg",
            params={"src": self.src},
        )
        response.raise_for_status()
        return response.content

    def probe(self) -> tuple[bool, float]:
        """Quick reachability check of the frame path.

        Returns (served_ok, elapsed_seconds). Used to tell apart a
        stalled snapshot/keyframe path from a fully dead feed.
        """
        start = time.monotonic()
        try:
            response = httpx.get(
                f"{self.base_url}/api/frame.jpeg",
                params={"src": self.src},
                timeout=4.0,
            )
        except httpx.RequestError:
            return False, 0.0
        return (
            response.status_code == 200,
            time.monotonic() - start,
        )

    def close(self):
        self._client.close()
