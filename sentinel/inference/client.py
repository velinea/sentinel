import httpx


class InferenceClient:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def detect(self, image: bytes) -> list[dict]:
        response = httpx.post(
            f"{self.url}/detect",
            files={
                "file": ("snapshot.jpg", image, "image/jpeg"),
            },
            timeout=30.0,
        )

        response.raise_for_status()

        data = response.json()
        return data["detections"]