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

