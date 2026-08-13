import httpx

from sentinel.detector.base import BaseDetector
from sentinel.detector.result import Detection, DetectionResult
from sentinel.snapshot import Snapshot


class HttpDetector(BaseDetector):

    def __init__(self, url: str):
        self.client = httpx.Client(
            base_url=url,
            timeout=30,
        )

    def detect(self, snapshot: Snapshot) -> DetectionResult:
        response = self.client.post(
            "/v1/vision/detection",
            files={
                "image": (
                    "snapshot.jpg",
                    snapshot.image,
                    "image/jpeg",
                )
            },
        )

        response.raise_for_status()

        data = response.json()

        detections = []

        for prediction in data.get("predictions", []):
            detections.append(
                Detection(
                    label=prediction["label"],
                    confidence=prediction["confidence"],
                    x_min=prediction["x_min"],
                    y_min=prediction["y_min"],
                    x_max=prediction["x_max"],
                    y_max=prediction["y_max"],
                )
            )

        return DetectionResult(detections=detections)
