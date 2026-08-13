from dataclasses import dataclass
from datetime import datetime


@dataclass
class Snapshot:
    camera: str
    timestamp: datetime
    image: bytes
