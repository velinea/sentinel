import yaml
from pydantic import BaseModel, Field


class HomeAssistantConfig(BaseModel):
    url: str
    token: str


class CameraConfig(BaseModel):
    name: str
    entity: str
    objects: list[str]


class InferenceConfig(BaseModel):
    backend: str
    url: str
    confidence: float = Field(ge=0.0, le=1.0)


class PollingConfig(BaseModel):
    idle_interval: int = Field(gt=0)
    active_interval: int = Field(gt=0)
    error_interval: int = Field(gt=0)


class TrackingConfig(BaseModel):
    movement_threshold: float = Field(ge=0.0)


class StorageConfig(BaseModel):
    path: str
    save_detections: bool


class Config(BaseModel):
    homeassistant: HomeAssistantConfig
    cameras: list[CameraConfig]
    inference: InferenceConfig
    polling: PollingConfig
    tracking: TrackingConfig
    storage: StorageConfig

def load_config(filename="config.yaml") -> Config:
    with open(filename, "r") as f:
        raw = yaml.safe_load(f)

    return Config.model_validate(raw)