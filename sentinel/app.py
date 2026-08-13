from sentinel.config import load_config
from sentinel.ha.client import HomeAssistantClient
from sentinel.storage.snapshots import SnapshotStorage
from sentinel.inference.client import InferenceClient


def main():
    config = load_config()

    client = HomeAssistantClient(
        config.homeassistant.url,
        config.homeassistant.token,
    )

    storage = SnapshotStorage(config.storage.path)

    inference = InferenceClient(
        config.detector.url,
    )

    print("Sentinel starting...")
    print(f"HA: {config.homeassistant.url}")
    print(f"Cameras: {len(config.cameras)}")

    for camera in config.cameras:
        print(f"\nProcessing {camera.name}...")

        image = client.get_snapshot(camera.entity)

        detections = inference.detect(image)

        interesting = [
            detection
            for detection in detections
            if (
                detection.label in camera.objects
                and detection.confidence >= config.detector.confidence
            )
        ]

        if interesting:
            storage.save(camera.name, image)

            for detection in interesting:
                print(
                    f"  {detection.label}: "
                    f"{detection.confidence:.2f}"
                )
        else:
            print("  No interesting detections")