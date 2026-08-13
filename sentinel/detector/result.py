from dataclasses import dataclass

@dataclass
class Detection:
    label: str
    confidence: float
    x_min: int
    y_min: int
    x_max: int
    y_max: int

@dataclass
class DetectionResult:
    detections: list[Detection]
