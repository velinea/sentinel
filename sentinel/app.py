from html import entities
import logging
import time

import httpx

from sentinel.camera import CameraState
from sentinel.config import load_config
from sentinel.ha.client import HomeAssistantClient
from sentinel.inference.client import InferenceClient
from sentinel.logging import setup_logging
from sentinel.storage.snapshots import SnapshotStorage

logger = logging.getLogger(__name__)


def main():
    setup_logging()

    config = load_config()

    client = HomeAssistantClient(
        config.homeassistant.url,
        config.homeassistant.token,
    )

    storage = SnapshotStorage(config.storage.path)

    inference = InferenceClient(
        config.inference.url,
    )

    states = {
        camera.name: CameraState(
            config.tracking.movement_threshold
        )
        for camera in config.cameras
    }

    next_poll = {
        camera.name: 0.0
        for camera in config.cameras
    }

    logger.info("Sentinel starting")
    logger.info("HA: %s", config.homeassistant.url)
    logger.info("Cameras: %d", len(config.cameras))
    camera_entities = client.get_camera_entities()
    logger.info("Discovered cameras:")

    for entity in camera_entities:
        logger.info("  %s", entity)


    while True:
        now = time.monotonic()

        for camera in config.cameras:
            if now < next_poll[camera.name]:
                continue

            state = states[camera.name]

            logger.info(
                "Processing %s",
                camera.name,
            )

            try:
                image = client.get_snapshot(
                    camera.entity
                )

                detections = inference.detect(image)

                interesting = [
                    detection
                    for detection in detections
                    if (
                        detection.label in camera.objects
                        and detection.confidence
                        >= config.inference.confidence
                    )
                ]

                changed = state.update(interesting)

                if changed:
                    if config.storage.save_detections:
                        filename = storage.save(
                            camera.name,
                            image,
                        )

                        logger.info(
                            "Activity detected: %s "
                            "→ saved %s",
                            ", ".join(
                                detection.label
                                for detection in changed
                            ),
                            filename,
                        )
                    else:
                        logger.info(
                            "Activity detected: %s",
                            ", ".join(
                                detection.label
                                for detection in changed
                            ),
                        )

                elif interesting:
                    logger.info(
                        "Objects stationary - "
                        "duplicate suppressed"
                    )

                else:
                    logger.info(
                        "No interesting detections"
                    )

                if state.is_active():
                    interval = (
                        config.polling.active_interval
                    )
                else:
                    interval = (
                        config.polling.idle_interval
                    )

            except httpx.HTTPStatusError as error:
                logger.error(
                    "%s: Home Assistant returned "
                    "HTTP %s",
                    camera.name,
                    error.response.status_code,
                )

                interval = config.polling.error_interval

            except httpx.RequestError as error:
                logger.error(
                    "%s: Network error: %s",
                    camera.name,
                    error,
                )

                interval = config.polling.error_interval

            except Exception:
                logger.exception(
                    "%s: Unexpected error",
                    camera.name,
                )

                interval = config.polling.error_interval

            next_poll[camera.name] = (
                time.monotonic() + interval
            )

        time.sleep(0.1)