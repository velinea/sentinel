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

    def close(self):
        self._client.close()
