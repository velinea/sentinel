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
    objects: list[str]
    interval: int = 10


@dataclass
class DetectorConfig:
    backend: str
    url: str
    confidence: float


@dataclass
class PollingConfig:
    idle_interval: int
    active_interval: int
    error_interval: int


@dataclass
class TrackingConfig:
    movement_threshold: float


@dataclass
class StorageConfig:
    path: str
    save_detections: bool


@dataclass
class Config:
    homeassistant: HomeAssistantConfig
    cameras: list[CameraConfig]
    detector: DetectorConfig
    polling: PollingConfig
    tracking: TrackingConfig
    storage: StorageConfig


def load_config(filename="config.yaml") -> Config:
    with open(filename, "r") as f:
        raw = yaml.safe_load(f)

    return Config(
        homeassistant=HomeAssistantConfig(
            **raw["homeassistant"]
        ),
        cameras=[
            CameraConfig(**camera)
            for camera in raw["cameras"]
        ],
        detector=DetectorConfig(
            **raw["detector"]
        ),
        polling=PollingConfig(
            **raw["polling"]
        ),
        tracking=TrackingConfig(
            **raw["tracking"]
        ),
        storage=StorageConfig(
            **raw["storage"]
        ),
    )