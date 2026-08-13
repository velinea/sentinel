from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import yaml


@dataclass
class HomeAssistantConfig:
    url: str
    token: str


@dataclass
class CameraConfig:
    name: str
    entity: str
    interval: int

@dataclass
class DetectorConfig:
    backend: str
    url: str

@dataclass
class StorageConfig:
    path: str

@dataclass
class Snapshot:
    camera: str
    timestamp: datetime
    image: bytes

@dataclass
class Config:
    homeassistant: HomeAssistantConfig
    detector: DetectorConfig
    storage: StorageConfig
    cameras: list[CameraConfig]

def load_config(filename="config.yaml") -> Config:
    with open(filename, "r") as f:
        raw = yaml.safe_load(f)

    return Config(
        homeassistant=HomeAssistantConfig(**raw["homeassistant"]),
        detector=DetectorConfig(**raw["detector"]),
        storage=StorageConfig(**raw["storage"]),
        cameras=[
            CameraConfig(**camera)
            for camera in raw["cameras"]
        ],
    )
