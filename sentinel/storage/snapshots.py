from pathlib import Path


class SnapshotStorage:

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, camera_name: str, image: bytes):

        filename = self.base_path / f"{camera_name}.jpg"

        with filename.open("wb") as f:
            f.write(image)
