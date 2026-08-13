from abc import ABC, abstractmethod

from sentinel.snapshot import Snapshot
from sentinel.detector.result import DetectionResult


class BaseDetector(ABC):

    @abstractmethod
    def detect(self, snapshot: Snapshot) -> DetectionResult:
        """Analyze a snapshot and return detected objects."""
        pass
