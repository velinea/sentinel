from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from sentinel.config import load_config

config = load_config()
storage = Path(config.storage.path)
clips_path = Path(config.clips.save_path)

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/latest/{camera}.jpg")
def latest_image(camera: str):
    image = storage / camera / "latest.jpg"

    if not image.exists():
        raise HTTPException(
            status_code=404,
            detail="No image available",
        )

    return FileResponse(
        image,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache",
        },
    )

@app.get("/latest/{camera}.mp4")
def latest_clip(camera: str):
    camera_dir = clips_path / camera

    if not camera_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="No clips available",
        )

    clips = sorted(
        camera_dir.glob("*.mp4"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not clips:
        raise HTTPException(
            status_code=404,
            detail="No clips available",
        )

    return FileResponse(
        clips[0],
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-cache",
        },
    )