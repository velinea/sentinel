import time

import httpx

from sentinel.camera import CameraState
from sentinel.config import load_config
from sentinel.ha.client import HomeAssistantClient
from sentinel.inference.client import InferenceClient
from sentinel.storage.snapshots import SnapshotStorage


IDLE_INTERVAL = 15
ACTIVE_INTERVAL = 5
ERROR_INTERVAL = 15


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

    states = {
        camera.name: CameraState()
        for camera in config.cameras
    }

    next_poll = {
        camera.name: 0.0
        for camera in config.cameras
    }

    print("Sentinel starting...")
    print(f"HA: {config.homeassistant.url}")
    print(f"Cameras: {len(config.cameras)}")

    while True:
        now = time.monotonic()

        for camera in config.cameras:
            if now < next_poll[camera.name]:
                continue

            state = states[camera.name]

            print(f"\nProcessing {camera.name}...")

            try:
                image = client.get_snapshot(camera.entity)

                detections = inference.detect(image)

                interesting = [
                    detection
                    for detection in detections
                    if (
                        detection.label in camera.objects
                        and detection.confidence
                        >= config.detector.confidence
                    )
                ]

                changed = state.update(interesting)

                if changed:
                    storage.save(camera.name, image)

                    print("  Activity:")

                    for detection in changed:
                        print(
                            f"    {detection.label}: "
                            f"{detection.confidence:.2f}"
                        )

                elif interesting:
                    print(
                        "  Objects stationary - "
                        "duplicate suppressed"
                    )

                else:
                    print("  No interesting detections")

                if state.is_active():
                    interval = ACTIVE_INTERVAL
                else:
                    interval = IDLE_INTERVAL

            except httpx.HTTPStatusError as error:
                print(
                    f"  ERROR: Home Assistant returned "
                    f"HTTP {error.response.status_code}"
                )
                interval = ERROR_INTERVAL

            except httpx.RequestError as error:
                print(
                    f"  ERROR: Network error: {error}"
                )
                interval = ERROR_INTERVAL

            except Exception as error:
                print(
                    f"  ERROR: Unexpected error: {error}"
                )
                interval = ERROR_INTERVAL

            next_poll[camera.name] = (
                time.monotonic() + interval
            )

        time.sleep(0.1)