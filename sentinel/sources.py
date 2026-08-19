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
        self.client = httpx.Client(base_url=url, timeout=10.0)
        self.src = src

    def get_snapshot(self) -> bytes:
        response = self.client.get(
            "/api/frame.jpeg",
            params={"src": self.src},
        )
        response.raise_for_status()
        return response.content
