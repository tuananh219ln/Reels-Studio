"""Entrance and exit motion for PC Shopee's drawn text (docs/decisions/2026-11-27-pc-text-motion.md).

A picture that moves needs no looped input of its own here: it is replaced by a few still pictures, each a little larger or
fainter than the last and shown for a slice of the motion's seconds, then the picture itself for the rest. The slices
follow each other with no gap, so the text is never missing for a frame. Cost: a few more overlays per step, kept small
(POP_FRAMES, CLEAR_FRAMES) because a long "Cộng dồn" video lays hundreds of steps.
"""

from dataclasses import dataclass

from PIL import Image

POP_SECONDS = 0.18  # a phrase's first word: from 115% and clear to 100% and sharp
CLEAR_SECONDS = 0.15  # the phrase ends: it fades out
POP_FRAMES, CLEAR_FRAMES = 2, 2
POP_SCALE = 1.15


@dataclass(frozen=True)
class Frame:
    """One still picture, its corner in the video's frame and the seconds it is shown."""

    image: Image.Image
    left: int
    top: int
    start: float
    end: float


def ease_out(progress: float) -> float:
    """Fast at first, settling at the end (cubic): how a pop arrives."""
    return 1 - (1 - min(1.0, max(0.0, progress))) ** 3


def transformed(
    picture: Image.Image, left: int, top: int, scale: float, opacity: float
) -> tuple[Image.Image, int, int]:
    """The picture scaled about its centre and made `opacity` as opaque, with the corner that keeps the centre where it was."""
    width, height = max(1, round(picture.width * scale)), max(1, round(picture.height * scale))
    image = picture if (width, height) == picture.size else picture.resize((width, height), Image.Resampling.LANCZOS)
    if opacity < 1:
        image = image.copy()
        image.putalpha(image.getchannel("A").point(lambda value: round(value * opacity)))
    return image, left + (picture.width - width) // 2, top + (picture.height - height) // 2


def entrance(
    picture: Image.Image,
    left: int,
    top: int,
    start: float,
    end: float,
    seconds: float = POP_SECONDS,
    frames: int = POP_FRAMES,
    scale: float = POP_SCALE,
    faint: bool = True,
) -> list[Frame]:
    """The picture arriving over `seconds` (shortened to the span): `frames` stills going from `scale` to 1 and, when
    `faint`, from clear to opaque, then the picture itself to `end`. The first still is already visible a little, so the
    first video frame is never empty."""
    span = min(seconds, end - start)
    out: list[Frame] = []
    if span > 0.02:
        for number in range(frames):
            ease = ease_out((number + 0.5) / frames)
            image, x, y = transformed(
                picture, left, top, scale + (1 - scale) * ease, (0.35 + 0.65 * ease) if faint else 1.0
            )
            out.append(Frame(image, x, y, start + span * number / frames, start + span * (number + 1) / frames))
    held = start + (span if out else 0)
    if end - held > 0.001:
        out.append(Frame(picture, left, top, held, end))
    return out


def departure(
    picture: Image.Image,
    left: int,
    top: int,
    start: float,
    end: float,
    seconds: float = CLEAR_SECONDS,
    frames: int = CLEAR_FRAMES,
) -> list[Frame]:
    """The picture to `end`, fading out over its last `seconds` in `frames` stills (opacity falling to nothing)."""
    span = min(seconds, (end - start) / 2)
    if span <= 0.02:
        return [Frame(picture, left, top, start, end)]
    cut = end - span
    out = [Frame(picture, left, top, start, cut)]
    for number in range(frames):
        image, x, y = transformed(picture, left, top, 1.0, 1 - (number + 1) / (frames + 1))
        out.append(Frame(image, x, y, cut + span * number / frames, cut + span * (number + 1) / frames))
    return out


def animate(
    picture: Image.Image, left: int, top: int, start: float, end: float, opens: bool, clears: bool
) -> list[Frame]:
    """A cumulative step: the first one of a phrase pops in (115% to 100%, clear to sharp), a later one just appears (a pop
    for each word would triple the pictures of a long video), and the last one of a phrase fades out at its end.
    Pictures follow each other with no gap from `start` to `end`."""
    frames = entrance(picture, left, top, start, end) if opens else [Frame(picture, left, top, start, end)]
    if not clears:
        return frames
    # The fade works on the step's last picture only: the steady one, or the whole of a short step.
    *before, last = frames
    return [*before, *departure(last.image, last.left, last.top, last.start, last.end)]
