# Configuration

**Configuration philosophy:** Sentinel aims to provide sensible defaults and a small number of clearly defined options. Most installations should only need to configure the Home Assistant connection, inference server, and camera list.

## Configuration file

All Sentinel settings are stored in a single file:

```
config.yaml
```

Sentinel loads the configuration during startup and validates it before processing any cameras.

## Global settings

### Snapshot polling

```yaml
polling:
  idle_interval: 5
  active_interval: 3
  error_interval: 15
```

| Setting | Description |
|---------|-------------|
| idle_interval | Poll interval (seconds) when no activity is detected |
| active_interval | Poll interval during activity |
| error_interval | Poll interval after an error (backoff) |

### Inference

```yaml
inference:
  url: http://sentinel-inference:8000
  min_confidence: 0.7
```

| Setting | Description |
|---------|-------------|
| url | REST endpoint of the inference server |
| min_confidence | Minimum detection confidence (0.0 - 1.0) |

### Storage

```yaml
storage:
  path: /path/to/snapshots
  save_detections: true
  retention_days: 30
  max_snapshots_per_camera: 500
```

| Setting | Description |
|---------|-------------|
| path | Directory where detection snapshots are saved |
| save_detections | Save snapshot images when activity is detected |
| retention_days | Delete snapshots older than N days (optional) |
| max_snapshots_per_camera | Keep at most N snapshots per camera (optional) |

Cleanup runs on startup and periodically during operation.

### Activity mode

```yaml
activity:
  movement_threshold: 30
```

| Setting | Description |
|---------|-------------|
| movement_threshold | Pixel distance for object movement detection |

```text
Person detected
      │
      ▼
Activity starts
      │
Every new detection
extends activity
      │
Object moves < 30px
      │
      ▼
Duplicate suppressed
      │
Object moves > 30px
      │
      ▼
Activity recorded
```

### Logging

```yaml
logging:
  level: INFO
```

| Setting | Description |
|---------|-------------|
| level | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Home Assistant

```yaml
homeassistant:
  url: http://homeassistant:8123
  token: YOUR_LONG_LIVED_ACCESS_TOKEN
```

| Setting | Description |
|---------|-------------|
| url | Home Assistant base URL |
| token | Long-lived access token for the REST API |

### go2rtc (optional)

If you run [go2rtc](https://github.com/AlexxIT/go2rtc) (e.g. as a Home Assistant add-on), Sentinel can pull snapshots directly from its HTTP API instead of going through the Home Assistant camera proxy. This reduces latency and avoids HA proxy overhead.

```yaml
go2rtc:
  url: http://localhost:1984
```

| Setting | Description |
|---------|-------------|
| url | Base URL of the go2rtc instance |

When using go2rtc, set `source: go2rtc` and `go2rtc_src` on individual cameras (see below).

### Video clips (optional)

Sentinel can record video clips when activity is detected. It maintains a rolling buffer in RAM and saves an MP4 clip covering the seconds before and after detection.

Requires `ffmpeg` to be installed on the system.

```yaml
clips:
  enabled: true
  buffer_seconds: 10
  post_seconds: 5
  max_seconds: 60
  save_path: /home/sentinel/sentinel/clips
  crf: 23
  fps: 10
```

| Setting | Description |
|---------|-------------|
| enabled | Enable clip recording (default: `false`) |
| buffer_seconds | Seconds of pre-event video kept in RAM |
| post_seconds | Seconds to capture after activity ends |
| max_seconds | Maximum clip length when activity continues |
| save_path | Directory where clips are saved |
| crf | H.264 encoding quality (lower = better, 0-51) |
| fps | Frames per second for the output clip |

Clips are only available for go2rtc cameras. Each camera's clips are saved in a subdirectory:

```
clips/
  front_door/
    front_door_20260819_143022.mp4
    front_door_20260819_143105.mp4
```

The latest clip is served at `GET /latest/{camera}.mp4` on the HTTP server.

Per-camera overrides:

```yaml
cameras:
  - name: front_door
    source: go2rtc
    go2rtc_src: cam0_sub
    clip_enabled: true
    clip_max_seconds: 120
    objects:
      - person
```

### Cameras

Each camera defines a name, a Home Assistant entity, and which objects should trigger detection.

```yaml
cameras:
  - name: front_door
    entity: camera.front_door
    objects:
      - person
      - cat
```

| Field | Description |
|-------|-------------|
| name | Camera identifier (used for storage paths and HTTP endpoint) |
| entity | Home Assistant camera entity ID |
| objects | Object labels that trigger a detection |
| source | Snapshot source: `ha` (default) or `go2rtc` |
| go2rtc_src | go2rtc stream name (required when `source: go2rtc`) |
| go2rtc_save_src | go2rtc stream name for high-res saves (optional) |
| notify | Fire a `sentinel_detection` event on activity (default: `false`) |
| notify_title | Event title (defaults to camera name) |
| clip_enabled | Enable clip recording for this camera (overrides global) |
| clip_max_seconds | Maximum clip length for this camera (overrides global) |

#### Home Assistant events

When activity is detected, Sentinel fires a custom event on the Home Assistant event bus. Enable it per camera:

```yaml
cameras:
  - name: front_door
    entity: camera.terassi_sannce_1
    notify: true
    notify_title: "Front Door"
    objects:
      - person
      - cat
```

The event type is `sentinel_detection` with the following payload:

| Field | Description |
|-------|-------------|
| title | Camera display title (`notify_title` or camera name) |
| camera | Camera name |
| objects | List of detected object labels |
| image_url | Link to the latest snapshot (only if `image_base_url` is set) |

To include the snapshot image URL, configure the base URL of the Sentinel HTTP server:

```yaml
notification:
  image_base_url: http://sentinel:8080
```

The event does not show anything in Home Assistant by itself — create an automation to act on it:

```yaml
alias: Sentinel Front Door Detection
trigger:
  platform: event
  event_type: sentinel_detection
  event_data:
    camera: front_door
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "{{ trigger.event.data.title }}"
      message: "Detected: {{ trigger.event.data.objects | join(', ') }}"
      data:
        image: "{{ trigger.event.data.image_url }}"
mode: single
```

The `image_url` is optional in the notification payload if `image_base_url` is not configured.

#### Using go2rtc as snapshot source

To pull snapshots directly from go2rtc instead of the Home Assistant camera proxy:

```yaml
go2rtc:
  url: http://localhost:1984

cameras:
  - name: front_door
    entity: camera.terassi_sannce_1
    source: go2rtc
    go2rtc_src: cam0_sub
    objects:
      - person
      - cat
```

The `go2rtc_src` value corresponds to the stream name in your go2rtc configuration. You can mix HA and go2rtc sources across cameras.

#### High-res archive snapshots

By default, Sentinel saves the same snapshot used for detection. If you detect on a sub-stream (fast, low bandwidth), the saved image will also be sub-stream quality.

To save high-res snapshots from the main stream while detecting on the sub-stream, set `go2rtc_save_src`:

```yaml
go2rtc:
  url: http://localhost:1984

cameras:
  - name: front_door
    entity: camera.terassi_sannce_1
    source: go2rtc
    go2rtc_src: cam0_sub
    go2rtc_save_src: cam0_main
    objects:
      - person
      - cat
```

When activity is detected, Sentinel fetches a fresh frame from the main stream before saving. The second fetch only happens on actual detections, so idle polling remains fast. If the main stream fetch fails, Sentinel falls back to saving the detection image and logs a warning.

## Complete example

```yaml
homeassistant:
  url: http://192.168.1.252:8123
  token: YOUR_LONG_TOKEN

inference:
  url: http://192.168.1.14:8000
  min_confidence: 0.7

polling:
  idle_interval: 5
  active_interval: 3
  error_interval: 15

activity:
  movement_threshold: 30

storage:
  path: /home/sentinel/sentinel/snapshots
  save_detections: true
  retention_days: 30
  max_snapshots_per_camera: 500

logging:
  level: INFO

go2rtc:
  url: http://localhost:1984

cameras:
  - name: front_door
    entity: camera.terassi_sannce_1
    source: go2rtc
    go2rtc_src: cam0_sub
    go2rtc_save_src: cam0
    notify: true
    notify_title: "Front Door"
    objects:
      - person
      - cat

  - name: front_yard
    entity: camera.piha_sannce_2
    objects:
      - person
      - car

  - name: garage
    entity: camera.piha_sannce_3
    objects:
      - person
      - car
      - truck

  - name: driveway
    entity: camera.piha_sannce_4
    objects:
      - person
      - car
      - truck

  - name: garden
    entity: camera.reolink_fluent
    notify: true
    objects:
      - person
      - dog
      - cat
```
