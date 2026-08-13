import httpx

from sentinel.detection import Detection


class InferenceClient:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def detect(self, image: bytes) -> list[Detection]:
        response = httpx.post(
            f"{self.url}/detect",
            files={
                "file": ("snapshot.jpg", image, "image/jpeg"),
            },
            timeout=30.0,
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