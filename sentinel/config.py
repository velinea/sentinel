from typing import Literal

import yaml
from pydantic import BaseModel, Field


class HomeAssistantConfig(BaseModel):
    url: str
    token: str


class Go2rtcConfig(BaseModel):
    url: str


class CameraConfig(BaseModel):
    name: str
    entity: str
    objects: list[str]
    source: Literal["ha", "go2rtc"] = "ha"
    go2rtc_src: str | None = None
    go2rtc_save_src: str | None = None
    notify: bool = False
    notify_title: str | None = None
    clip_enabled: bool | None = None
    clip_max_seconds: int | None = None


class InferenceConfig(BaseModel):
    url: str
    min_confidence: float = Field(ge=0.0, le=1.0)


class PollingConfig(BaseModel):
    idle_interval: int = Field(gt=0)
    active_interval: int = Field(gt=0)
    error_interval: int = Field(gt=0)


class ActivityConfig(BaseModel):
    movement_threshold: float = Field(ge=0.0)


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class StorageConfig(BaseModel):
    path: str
    save_detections: bool
    retention_days: int | None = None
    max_snapshots_per_camera: int | None = None


class NotificationConfig(BaseModel):
    image_base_url: str | None = None


class ClipConfig(BaseModel):
    enabled: bool = False
    buffer_seconds: int = Field(default=10, gt=0)
    max_seconds: int = Field(default=60, gt=0)
    save_path: str = "clips"
    crf: int = Field(default=23, ge=0, le=51)
    fps: int = Field(default=10, gt=0)


class WebConfig(BaseModel):
    auth_user: str | None = None
    auth_password: str | None = None


class Config(BaseModel):
    homeassistant: HomeAssistantConfig
    cameras: list[CameraConfig]
    inference: InferenceConfig
    polling: PollingConfig
    activity: ActivityConfig
    storage: StorageConfig
    go2rtc: Go2rtcConfig | None = None
    logging: LoggingConfig = LoggingConfig()
    notification: NotificationConfig = NotificationConfig()
    clips: ClipConfig = ClipConfig()
    web: WebConfig = WebConfig()


def load_config(filename="config.yaml") -> Config:
    with open(filename, "r") as f:
        raw = yaml.safe_load(f)

    return Config.model_validate(raw)