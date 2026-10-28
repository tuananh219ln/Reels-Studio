import math
from dataclasses import dataclass

FPS = 30
XFADE_FRAMES = 12  # 0.4s, split evenly around each scene boundary
HALF_XFADE = XFADE_FRAMES // 2


@dataclass(frozen=True)
class Timeline:
    scene_frames: list[int]
    clip_frames: list[int]
    xfade_offsets: list[int]
    total_frames: int

    @property
    def total_seconds(self) -> float:
        return self.total_frames / FPS


def to_frames(seconds: float) -> int:
    return math.floor(seconds * FPS + 0.5)


def build_timeline(seconds: list[float]) -> Timeline:
    """Frame-exact plan where total length equals the summed seconds.

    Boundaries are rounded cumulatively so rounding error never accumulates past half a frame.
    Each clip is extended by half a crossfade on every side that touches a neighbour, so the
    crossfade straddles the boundary instead of eating into the total.
    """
    if len(seconds) < 2:
        raise ValueError("a timeline needs the title scene and at least one content scene")
    boundaries = [0]
    elapsed = 0.0
    for value in seconds:
        elapsed += value
        boundaries.append(to_frames(elapsed))
    scene_frames = [end - start for start, end in zip(boundaries, boundaries[1:])]

    last = len(scene_frames) - 1
    clip_frames = [
        frames + (HALF_XFADE if index > 0 else 0) + (HALF_XFADE if index < last else 0)
        for index, frames in enumerate(scene_frames)
    ]
    return Timeline(
        scene_frames=scene_frames,
        clip_frames=clip_frames,
        xfade_offsets=[boundary - HALF_XFADE for boundary in boundaries[1:-1]],
        total_frames=boundaries[-1],
    )
