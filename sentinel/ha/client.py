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
