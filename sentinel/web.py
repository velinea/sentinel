from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from sentinel.config import load_config

config = load_config()
storage = Path(config.storage.path)

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