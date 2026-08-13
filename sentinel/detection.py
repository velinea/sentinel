from dataclasses import dataclass


@dataclass
class Detection:
    label: str
    confidence: float
    box: list[int]