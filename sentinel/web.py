from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

SNAPSHOT_PATH = "/home/sentinel/sentinel/snapshots"


app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/latest/{camera}.jpg")
def latest_image(camera: str):
    image = Path(SNAPSHOT_PATH) / camera / "latest.jpg"

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