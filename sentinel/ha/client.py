from html import entities

import httpx


class HomeAssistantClient:

    def __init__(self, url: str, token: str):

        self.client = httpx.Client(
            base_url=url,
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=15,
        )

    def get_snapshot(self, entity: str) -> bytes:

        response = self.client.get(
            f"/api/camera_proxy/{entity}"
        )

        response.raise_for_status()

        return response.content

    def get_camera_entities(self):

        response = self.client.get("/api/states")

        response.raise_for_status()
        entities = response.json()
        for entity in entities:
            if entity["entity_id"].startswith("camera."):
                print(entity["entity_id"], entity["attributes"]["entity_picture"].partition("?")[0])
        camera_entities = [
            entity["entity_id"]
            for entity in entities
            if entity["entity_id"].startswith("camera.")
        ]
        return camera_entities