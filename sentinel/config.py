from dataclasses import dataclass
from pathlib import Path

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
    objects: list[str]


@dataclass
class DetectorConfig:
    backend: str
    url: str
    confidence: float


@dataclass
class StorageConfig:
    path: str


@dataclass
class Config:
    homeassistant: HomeAssistantConfig
    cameras: list[CameraConfig]
    detector: DetectorConfig
    storage: StorageConfig


def load_config(filename="config.yaml") -> Config:
    with open(filename, "r") as f:
        raw = yaml.safe_load(f)

    return Config(
        homeassistant=HomeAssistantConfig(**raw["homeassistant"]),
        cameras=[
            CameraConfig(**camera)
            for camera in raw["cameras"]
        ],
        detector=DetectorConfig(**raw["detector"]),
        storage=StorageConfig(**raw["storage"]),
    )