import httpx

from sentinel.detection import Detection


class InferenceClient:
    def __init__(self, url: str):
        self.client = httpx.Client(
            base_url=url.rstrip("/"),
            timeout=30.0,
        )

    def detect(self, image: bytes) -> list[Detection]:
        response = self.client.post(
            "/detect",
            files={
                "file": ("snapshot.jpg", image, "image/jpeg"),
            },
        )

        response.raise_for_status()

        data = response.json()

        return [
            Detection(
                label=item["label"],
                confidence=item["confidence"],
                box=item["box"],
            )
            for item in data["detections"]
        ]