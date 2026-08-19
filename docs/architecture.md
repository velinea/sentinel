# Architecture

Sentinel is a lightweight AI snapshot detector for Home Assistant. It periodically polls camera snapshots, runs object detection via a dedicated inference server, and stores only interesting detections.

---

## Services

Sentinel is split into three services:

| Service | Role | Entry point |
|---------|------|-------------|
| **Sentinel** | Snapshot polling, filtering, activity tracking, storage | `sentinel` CLI / `sentinel.__main__:main` |
| **Sentinel HTTP** | FastAPI server exposing latest snapshots | `uvicorn sentinel.web:app` |
| **Sentinel Inference** | OpenVINO + YOLO inference (separate repo) | External |

Splitting the HTTP server and inference into separate processes keeps each service lightweight and independently restartable.

---

## Data flow

```
Home Assistant / go2rtc
        │
  Camera snapshots (JPEG)
        │
        v
   +-----------+
   | Sentinel  |
   |-----------|
   | 1. Poll   │  snapshots from HA or go2rtc
   | 2. Detect │  via inference server REST API
   | 3. Filter │  by per-camera object list
   | 4. Track  │  movement across frames
   | 5. Store  │  timestamped JPGs + latest.jpg
   | 6. Notify │  HA persistent notifications
   +-----+-----+
         │
    REST API
         │
         v
  +-------------------+
  | Sentinel Inference|
  | OpenVINO + YOLO   |
  +-------------------+
         │
    Detection results
    (label, confidence, box)
```

---

## Snapshot sources

Each camera is configured with a snapshot source:

- **HA camera proxy** (`source: ha`) — fetches snapshots via Home Assistant's `/api/camera_proxy/{entity}` endpoint. Requires a valid HA entity.
- **go2rtc** (`source: go2rtc`) — fetches snapshots directly from go2rtc's `/api/frame.jpeg?src=` endpoint. Lower latency, no HA proxy overhead.

The source is selected per camera in `config.yaml`. Cameras can be mixed freely between the two sources.

---

## Activity tracking

When detections are found, Sentinel tracks objects across frames using spatial proximity matching:

1. Each detection's bounding box center is computed
2. It is matched to a previously tracked object by label and nearest center position
3. If no match exists (new object) or the object has moved beyond `movement_threshold` pixels, the detection is counted as a change
4. If the object is stationary (within threshold), the detection is suppressed as a duplicate

This prevents repeated storage/notifications for objects sitting still while still capturing movement.

```
Object detected at (100, 200)
        │
        v
Matched to previous (102, 198)?
  Distance = 2.8px < 30px threshold
        │
        v
Duplicate suppressed
```

---

## Storage

Snapshots are stored per camera in the configured `storage.path`:

```
snapshots/
  front_door/
    20260819_143022.jpg
    20260819_143025.jpg
    latest.jpg
  driveway/
    20260819_143022.jpg
    latest.jpg
```

- **Timestamped files** — archive of all detected activity
- **`latest.jpg`** — overwritten on each save, served by the HTTP server
- **Cleanup** — runs on startup and periodically, enforcing `retention_days` and `max_snapshots_per_camera`

---

## HTTP server

The FastAPI server (`sentinel.web`) exposes:

| Endpoint | Response |
|----------|----------|
| `GET /health` | `{"status": "ok"}` |
| `GET /latest/{camera}.jpg` | Latest detection snapshot (JPEG, no-cache) |

Intended to be consumed by Home Assistant's Generic Camera integration.

---

## Error handling

Each camera is processed independently. Errors on one camera do not affect others. After an error, that camera's polling interval increases to `error_interval` (default 15s) before retrying.

Three error categories:

1. **HTTP errors** — HA or inference server returned 4xx/5xx
2. **Network errors** — connection refused, timeout, DNS failure
3. **Unexpected errors** — logged with full traceback

---

## Configuration

All settings live in a single `config.yaml` validated by Pydantic models at startup. See [configuration.md](configuration.md) for the full reference.

---

## Project layout

```
sentinel/
  __init__.py
  __main__.py         CLI entry point
  app.py              Main polling loop
  config.py           Pydantic config models
  camera.py           Activity tracking state
  detection.py        Detection dataclass
  sources.py          Snapshot source protocol + implementations
  web.py              FastAPI HTTP server
  logging.py          Logging setup
  ha/
    client.py         Home Assistant REST client
  inference/
    client.py         Inference server client
  storage/
    snapshots.py      Snapshot file storage + cleanup
```
