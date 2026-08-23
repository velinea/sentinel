# Sentinel

<div align="center">
  <img src=docs/sentinel.png alt="Sentinel logo" width="300"/>
</div>   

**Sentinel** is a lightweight AI snapshot detector for Home Assistant.

Instead of processing continuous RTSP video streams, Sentinel periodically polls camera snapshots already provided by Home Assistant, performs AI object detection using a dedicated inference server, and stores only interesting detections. This approach keeps the architecture simple, resource-efficient and easy to integrate into existing Home Assistant installations.

Sentinel was created as a modern replacement for DOODS, taking advantage of current YOLO models, OpenVINO acceleration and inexpensive Intel N100-class hardware.

---

## Features

- Snapshot-based object detection
- OpenVINO-accelerated YOLO inference
- Lightweight REST-based inference server
- Per-camera object filtering
- Configurable confidence thresholds
- Activity mode for ongoing events
- Automatic storage of interesting snapshots
- Latest detection exposed to Home Assistant
- go2rtc direct snapshot source (optional)
- Home Assistant detection events (for automations)
- Video clip recording with rolling buffer (optional)
- Automatic snapshot retention and cleanup
- Configurable logging levels
- Graceful shutdown handling
- Designed for low-power hardware

---

## Why snapshots instead of RTSP?

Most Home Assistant users already have camera snapshots available through the Home Assistant API.

For object detection, Sentinel only needs periodic images—not continuous video streams. By polling snapshots instead of decoding multiple RTSP streams, Sentinel:

- reduces CPU and memory usage
- avoids complex video pipelines
- keeps camera integration simple
- remains independent of camera vendors
- scales well for typical Home Assistant installations

The result is a detector that is significantly simpler than traditional NVR-based AI systems while still providing reliable object detection.

---

## Architecture

```text
    Home Assistant / go2rtc
              │
        Camera snapshots
              │
              ▼
       +--------------+
       |   Sentinel   |
       |--------------|
       | Snapshot poll|
       | Detection    |
       | Filtering    |
       | Activity     |
       | HTTP server  |
       +------+-------+
              │
        REST API
              │
              ▼
   +-------------------------+
   | Sentinel Inference      |
   | OpenVINO + YOLO         |
   +-------------------------+
              │
              ▼
       Detection results
```

Sentinel is intentionally split into three services:

- **Sentinel** handles snapshot polling, filtering, activity tracking, clip recording, storage and Home Assistant integration.
- **Sentinel HTTP** serves the web dashboard, latest snapshots, and video clips.
- **Sentinel Inference** performs AI inference using OpenVINO and exposes a simple REST API.

This separation allows the inference backend to evolve independently from the application logic.

---

## Hardware requirements

Sentinel is designed for modest hardware.

Recommended:

- Intel N100 or similar CPU
- Intel integrated graphics with OpenVINO support
- Debian or other modern Linux distribution
- Home Assistant

The project has been developed and tested using:

- Proxmox VE
- Debian 13 LXC containers
- Home Assistant OS
- Intel N100 Mini PC

---

## Project status

Sentinel is under active development.

Current functionality includes:

- Snapshot polling from HA or go2rtc
- YOLO/OpenVINO inference
- Per-camera object filtering
- Activity mode with movement tracking
- Web dashboard with camera grid
- HTTP snapshot and clip endpoints
- Snapshot storage with retention cleanup
- Video clip recording with rolling buffer
- Home Assistant sentinel_detection events
- Graceful camera error handling
- Configurable logging
- Graceful shutdown

Planned improvements include:

- Post-event clip padding (post_seconds)
- Docker packaging
- Expanded documentation

---

## Documentation

Additional documentation is available in the `docs` directory.

- Architecture
- Installation
- Configuration
- Developer notes

---

## License

[MIT](LICENCE)