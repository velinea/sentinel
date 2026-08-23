# Developer notes

## Prerequisites

- Python 3.13+
- A Home Assistant instance with camera entities
- The Sentinel Inference server running (separate service)
- Git
- ffmpeg (for video clip recording)

## Setting up a development environment

Clone the repository:

```bash
git clone https://github.com/velinea/sentinel.git
cd sentinel
```

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install in editable mode:

```bash
pip install -e .
```

Install dev tools:

```bash
pip install pyright
```

Copy the config:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your Home Assistant URL, token, inference server URL, and camera entities.

## Running locally

Start the main detection loop:

```bash
sentinel
```

Or run as a module:

```bash
python -m sentinel
```

The HTTP server runs separately:

```bash
uvicorn sentinel.web:app --host 0.0.0.0 --port 8001
```

## Type checking

```bash
pyright sentinel/
```

All code should pass with 0 errors before committing.

## Code style

- Python 3.13+ features are used freely (e.g. `X | None` union syntax)
- Pydantic v2 for all configuration models
- `httpx` for all HTTP clients (sync, with connection reuse via `httpx.Client`)
- Logging via the standard library `logging` module — use `logger = logging.getLogger(__name__)` per module
- No comments unless the logic is genuinely non-obvious
- Keep functions short and focused

## Project conventions

- **Config validation** — all user-facing config goes through Pydantic models in `config.py`. Invalid config should fail fast at startup.
- **Error handling** — the main loop catches per-camera errors and backs off. Individual services raise `httpx.HTTPStatusError` or `httpx.RequestError`.
- **Snapshot sources** — new snapshot backends implement the `SnapshotSource` protocol in `sources.py`.
- **Storage** — timestamped filenames (`YYYYMMDD_HHMMSS.jpg`) enable simple date-based cleanup.

## Testing

Tests are not yet written. When they are added, run with:

```bash
pytest
```

## Git workflow

- Work on feature branches off `main`
- Keep commits focused and messages concise
- Run `pyright` before committing
