import json
import logging
import signal
import time
from pathlib import Path

import httpx

from sentinel.camera import CameraState
from sentinel.clips import ClipManager
from sentinel.config import load_config
from sentinel.ha.client import HomeAssistantClient
from sentinel.inference.client import InferenceClient
from sentinel.logging import setup_logging
from sentinel.sources import Go2rtcSource, HASource, SnapshotSource
from sentinel.storage.snapshots import SnapshotStorage

logger = logging.getLogger(__name__)

shutdown_requested = False


def handle_shutdown(signum, frame):
    global shutdown_requested
    logger.info("Shutdown requested (signal %s)", signum)
    shutdown_requested = True


def write_status(status_path: Path, health: dict):
    data = {
        "cameras": {},
        "updated": time.time(),
    }
    for name, h in health.items():
        data["cameras"][name] = {
            "last_ok": h["last_ok"],
            "last_error": h["last_error"],
            "error": h["error"],
        }
    try:
        status_path.write_text(json.dumps(data))
    except OSError:
        pass


def check_consumers(config, sources):
    """Watchdog: warn if a go2rtc stream accumulates too many
    stale keyframe (snapshot) consumers. Returns True if any
    stream is unhealthy."""
    unhealthy = False

    urls: set[str] = set()
    for camera in config.cameras:
        if camera.source != "go2rtc":
            continue
        url = (
            camera.go2rtc_url
            or (config.go2rtc.url if config.go2rtc else None)
        )
        if url:
            urls.add(url)

    for url in urls:
        try:
            with httpx.Client(
                base_url=url,
                timeout=10.0,
            ) as client:
                response = client.get("/api/streams")
                response.raise_for_status()
                streams = response.json()
        except Exception as exc:
            logger.warning(
                "consumer-check: failed to query %s: %s",
                url, exc,
            )
            continue

        for sname, info in streams.items():
            if not isinstance(info, dict):
                continue
            consumers = info.get("consumers", [])
            stale = [
                c for c in consumers
                if (
                    isinstance(c, dict)
                    and c.get("format_name") == "keyframe"
                    and "httpx" in c.get("user_agent", "")
                )
            ]
            if len(stale) > 20:
                logger.warning(
                    "consumer-check: %s@%s has %d stale "
                    "snapshot consumers - restart go2rtc "
                    "to clear",
                    sname, url, len(stale),
                )
                unhealthy = True

    return unhealthy


def build_sources(config):
    ha_client = HomeAssistantClient(
        config.homeassistant.url,
        config.homeassistant.token,
    )

    sources: dict[str, SnapshotSource] = {}
    save_sources: dict[str, SnapshotSource] = {}

    for camera in config.cameras:
        if camera.source == "go2rtc":
            go2rtc_url = (
                camera.go2rtc_url
                or (config.go2rtc.url if config.go2rtc else None)
            )
            if go2rtc_url is None:
                raise ValueError(
                    f"Camera '{camera.name}' requires go2rtc "
                    "but no go2rtc url found"
                )
            if camera.go2rtc_src is None:
                raise ValueError(
                    f"Camera '{camera.name}' has "
                    "source: go2rtc but no go2rtc_src set"
                )
            sources[camera.name] = Go2rtcSource(
                go2rtc_url,
                camera.go2rtc_src,
            )
        else:
            sources[camera.name] = HASource(
                ha_client, camera.entity
            )

        if camera.go2rtc_save_src is not None:
            go2rtc_url = (
                camera.go2rtc_url
                or (config.go2rtc.url if config.go2rtc else None)
            )
            if go2rtc_url is None:
                raise ValueError(
                    f"Camera '{camera.name}' requires go2rtc "
                    "for go2rtc_save_src but no go2rtc "
                    "url found"
                )
            save_sources[camera.name] = Go2rtcSource(
                go2rtc_url,
                camera.go2rtc_save_src,
            )

    return ha_client, sources, save_sources


def main():
    config = load_config()

    setup_logging(config.logging.level)

    ha_client, sources, save_sources = build_sources(config)

    storage = SnapshotStorage(config.storage.path)

    clip_manager = ClipManager(config)
    clip_manager.start()

    inference = InferenceClient(
        config.inference.url,
    )

    states = {
        camera.name: CameraState(
            config.activity.movement_threshold
        )
        for camera in config.cameras
    }

    health: dict[str, dict] = {
        camera.name: {
            "last_ok": 0.0,
            "last_error": 0.0,
            "error": "",
        }
        for camera in config.cameras
    }
    status_path = Path(config.storage.path) / "status.json"

    next_poll = {
        camera.name: 0.0
        for camera in config.cameras
    }

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    cleanup_interval = 1000
    consumer_check_interval = 600
    loop_count = 0

    storage.cleanup(
        config.storage.retention_days,
        config.storage.max_snapshots_per_camera,
    )

    logger.info("Sentinel starting")
    logger.info("HA: %s", config.homeassistant.url)
    logger.info("Cameras: %d", len(config.cameras))

    for camera in config.cameras:
        source_type = camera.source
        logger.info(
            "  %s (%s)", camera.name, source_type
        )

    while not shutdown_requested:
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
                source = sources[camera.name]
                image = source.get_snapshot()

                detections = inference.detect(image)

                interesting = [
                    detection
                    for detection in detections
                    if (
                        detection.label in camera.objects
                        and detection.confidence
                        >= config.inference.min_confidence
                    )
                ]

                changed = state.update(interesting)

                if interesting:
                    clip_manager.notify_detection(
                        camera.name
                    )

                if changed:

                    if config.storage.save_detections:
                        save_image = image

                        if camera.name in save_sources:
                            try:
                                save_image = (
                                    save_sources[
                                        camera.name
                                    ].get_snapshot()
                                )
                            except Exception:
                                logger.warning(
                                    "%s: Save source "
                                    "fetch failed, "
                                    "using detection "
                                    "image",
                                    camera.name,
                                )

                        filename = storage.save(
                            camera.name,
                            save_image,
                        )

                        logger.info(
                            "Activity detected: %s "
                            "\u2192 saved %s",
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

                    if camera.notify:
                        event_data = {
                            "title": (
                                camera.notify_title
                                or camera.name
                            ),
                            "camera": camera.name,
                            "objects": [
                                detection.label
                                for detection in changed
                            ],
                        }

                        if (
                            config.notification
                            .image_base_url
                        ):
                            base = (
                                config.notification
                                .image_base_url
                                .rstrip("/")
                            )
                            event_data["image_url"] = (
                                f"{base}/latest/"
                                f"{camera.name}.jpg"
                            )

                        try:
                            ha_client.fire_event(
                                "sentinel_detection",
                                event_data,
                            )
                        except Exception:
                            logger.warning(
                                "%s: Event fire failed",
                                camera.name,
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

                health[camera.name]["last_ok"] = time.time()
                health[camera.name]["error"] = ""

            except httpx.HTTPStatusError as error:
                logger.error(
                    "%s: HTTP error %s",
                    camera.name,
                    error.response.status_code,
                )
                health[camera.name]["last_error"] = time.time()
                health[camera.name]["error"] = (
                    f"HTTP {error.response.status_code}"
                )

                interval = config.polling.error_interval

            except httpx.RequestError as error:
                logger.error(
                    "%s: Network error: %s",
                    camera.name,
                    error,
                )
                health[camera.name]["last_error"] = time.time()
                health[camera.name]["error"] = str(error)

                interval = config.polling.error_interval

            except Exception:
                logger.exception(
                    "%s: Unexpected error",
                    camera.name,
                )
                health[camera.name]["last_error"] = time.time()
                health[camera.name]["error"] = "Unexpected error"

                interval = config.polling.error_interval

            next_poll[camera.name] = (
                time.monotonic() + interval
            )

        time.sleep(0.1)

        loop_count += 1
        if loop_count % cleanup_interval == 0:
            storage.cleanup(
                config.storage.retention_days,
                config.storage.max_snapshots_per_camera,
            )

        if loop_count % 30 == 0:
            write_status(status_path, health)

        if loop_count % consumer_check_interval == 0:
            check_consumers(config, sources)

    clip_manager.shutdown()
    logger.info("Sentinel stopped")
