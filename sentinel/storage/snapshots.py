import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


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

    def save_latest(self, camera_name: str, image: bytes):
        camera_path = self.base_path / camera_name

        camera_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        (camera_path / "latest.jpg").write_bytes(image)

    def cleanup(
        self,
        retention_days: int | None = None,
        max_per_camera: int | None = None,
    ):
        for camera_dir in self.base_path.iterdir():
            if not camera_dir.is_dir():
                continue

            if camera_dir.name.startswith("."):
                continue

            snapshots = sorted(
                f
                for f in camera_dir.iterdir()
                if f.suffix == ".jpg"
                and f.name != "latest.jpg"
            )

            if retention_days is not None:
                cutoff = datetime.now() - timedelta(
                    days=retention_days
                )
                for snapshot in snapshots:
                    try:
                        date_str = snapshot.stem
                        file_date = datetime.strptime(
                            date_str, "%Y%m%d_%H%M%S"
                        )
                        if file_date < cutoff:
                            snapshot.unlink()
                            logger.debug(
                                "Deleted expired: %s",
                                snapshot,
                            )
                    except ValueError:
                        pass

                snapshots = sorted(
                    f
                    for f in camera_dir.iterdir()
                    if f.suffix == ".jpg"
                    and f.name != "latest.jpg"
                )

            if max_per_camera is not None:
                excess = (
                    len(snapshots) - max_per_camera
                )
                if excess > 0:
                    for snapshot in snapshots[:excess]:
                        snapshot.unlink()
                        logger.debug(
                            "Deleted excess: %s",
                            snapshot,
                        )