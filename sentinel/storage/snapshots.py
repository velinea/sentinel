from datetime import datetime
from pathlib import Path


class SnapshotStorage:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(
            parents=True,
            exist_ok=True,
        )

    def save(self, camera_name: str, image: bytes):
        camera_path = self.base_path / camera_name

        camera_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        filename = camera_path / f"{timestamp}.jpg"
        latest = camera_path / "latest.jpg"

        filename.write_bytes(image)
        latest.write_bytes(image)

        return filename