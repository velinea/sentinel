from dataclasses import dataclass, field
import math
import time

from sentinel.detection import Detection


MOVEMENT_THRESHOLD = 30


@dataclass
class TrackedObject:
    label: str
    center_x: float
    center_y: float
    last_seen: float


@dataclass
class CameraState:
    objects: list[TrackedObject] = field(default_factory=list)

    def update(self, detections: list[Detection]) -> list[Detection]:
        now = time.monotonic()

        new_objects: list[TrackedObject] = []
        changed: list[Detection] = []

        for detection in detections:
            center_x = (
                detection.box[0] + detection.box[2]
            ) / 2

            center_y = (
                detection.box[1] + detection.box[3]
            ) / 2

            match = self._find_match(
                detection.label,
                center_x,
                center_y,
            )

            if match is None:
                changed.append(detection)

            else:
                distance = math.hypot(
                    center_x - match.center_x,
                    center_y - match.center_y,
                )

                if distance >= MOVEMENT_THRESHOLD:
                    changed.append(detection)

            new_objects.append(
                TrackedObject(
                    label=detection.label,
                    center_x=center_x,
                    center_y=center_y,
                    last_seen=now,
                )
            )

        self.objects = new_objects

        return changed

    def is_active(self) -> bool:
        return bool(self.objects)

    def _find_match(
        self,
        label: str,
        center_x: float,
        center_y: float,
    ) -> TrackedObject | None:
        matches = [
            obj
            for obj in self.objects
            if obj.label == label
        ]

        if not matches:
            return None

        return min(
            matches,
            key=lambda obj: math.hypot(
                center_x - obj.center_x,
                center_y - obj.center_y,
            ),
        )