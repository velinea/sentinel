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

```
polling:
  idle_interval: 5
  active_interval: 3
```

| Setting | Description |
|---------|-------------|
| idle_interval	| Poll interval (seconds) when no  activity is detected |
| active_interval |	Poll interval during activity |

### Inference

```
inference:
  url: http://sentinel-inference:8000
  timeout: 10
```
| Setting |	Description |
| --------|-------------|
| url	| REST endpoint of the inference server |
| timeout	| Request timeout |

### Storage

```
storage:
  directory: snapshots
```

### Logging

```
logging:
  level: INFO
```

Supported values:

```
DEBUG
INFO
WARNING
ERROR
```
### Home Assistant

```
home_assistant:
  url:
  token:
```

### Cameras

Example:

```
cameras:

  driveway:
    entity: camera.driveway
    confidence: 0.70

    interesting:
      - person
      - car
      - truck

  backyard:
    entity: camera.backyard
    confidence: 0.60


    interesting:
      - person
      - dog
      - cat
```

| Field	| Description |
|-------|-------------|
| entity |Home Assistant camera entity |
| confidence	| Minimum confidence |
| interesting	| Objects that should trigger a snapshot |

### Activity mode
```
activity:
    timeout: 30
```
```
Person detected
      │
      ▼
Activity starts
      │
Every new detection
extends timer
      │
No detections
for 30 s
      │
      ▼
Activity ends
```

### HTTP server

```
http:
    host:
    port:
```
## Complete example
config.example.yaml:

```
homeassistant:
  url: http://<HOMEASSISTANT_IP>:8123
  token: YOUR_LONG_TOKEN

inference:
  backend: yolo
  url: http://<SENTINEL-INFERENCE_IP>:8000
  min_confidence: 0.7
  
polling:
  idle_interval: 5
  active_interval: 3
  error_interval: 15

activity:
  movement_threshold: 30

storage:
  path: "/PATH/TO/snapshots"
  save_detections: true

cameras:
  - name: front_door
    entity: camera.terassi_sannce_1
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
    objects:
      - person
      - dog
      - cat
```