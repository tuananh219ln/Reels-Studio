"""Sound effects made by FFmpeg itself (no sound files, so nothing to license), each a named preset, and a scene's
own music level. The api makes the same sound for the studio to play (GET /api/sounds/library/{name}.mp3).
Keep the labels in step with web/src/components/video/preview/sounds.ts.
"""

from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import find_tools, run

RATE = 48000


@dataclass(frozen=True)
class Sound:
    label: str
    source: str  # an FFmpeg source filter chain making it, mono at RATE
    seconds: float


@dataclass(frozen=True)
class Level:
    label: str
    gain: float


def _tone(expression: str, seconds: float) -> str:
    return f"aevalsrc='{expression}':s={RATE}:d={seconds}"


SOUNDS: dict[str, Sound] = {
    "whoosh": Sound(
        "Vút",
        f"anoisesrc=r={RATE}:d=0.6:c=pink:a=0.9,highpass=f=400,lowpass=f=3000,afade=t=in:d=0.25,afade=t=out:st=0.25:d=0.35",
        0.6,
    ),
    "swoosh": Sound(
        "Lướt nhanh",
        f"anoisesrc=r={RATE}:d=0.35:c=white:a=0.4,highpass=f=1500,afade=t=in:d=0.1,afade=t=out:st=0.1:d=0.25",
        0.35,
    ),
    "ding": Sound("Ting", _tone("0.6*sin(2*PI*1320*t)*exp(-5*t)+0.25*sin(2*PI*2640*t)*exp(-7*t)", 0.9), 0.9),
    "pop": Sound("Bụp", _tone("0.9*sin(2*PI*(520-1300*t)*t)*exp(-30*t)", 0.15), 0.15),
    "click": Sound("Tách", _tone("0.8*sin(2*PI*2200*t)*exp(-90*t)", 0.06), 0.06),
    "boom": Sound("Bùm", _tone("0.95*sin(2*PI*(90-20*t)*t)*exp(-3*t)", 1.2), 1.2),
    "rise": Sound("Dâng lên", _tone("0.35*sin(2*PI*(220+250*t)*t)*min(1,t)", 1.2) + ",afade=t=out:st=1.0:d=0.2", 1.2),
    "success": Sound(
        "Hoàn thành",
        _tone(
            "0.5*sin(2*PI*988*t)*exp(-6*t)*lt(t,0.14)+0.5*sin(2*PI*1319*t)*exp(-4*(t-0.14))*gte(t,0.14)",
            0.8,
        ),
        0.8,
    ),
    "wrong": Sound("Sai rồi", _tone("0.3*sgn(sin(2*PI*140*t))*exp(-2.5*t)", 0.6), 0.6),
    "coin": Sound(
        "Tiền về",
        _tone(
            "0.45*sin(2*PI*1568*t)*exp(-8*t)*lt(t,0.09)+0.45*sin(2*PI*2093*t)*exp(-5*(t-0.09))*gte(t,0.09)",
            0.7,
        ),
        0.7,
    ),
    "heartbeat": Sound("Nhịp tim", _tone("0.9*sin(2*PI*60*t)*(exp(-25*t)+exp(-25*abs(t-0.25))*gte(t,0.25))", 0.7), 0.7),
}

SOUND_VOLUMES: dict[str, Level] = {
    "soft": Level("Nhỏ", 0.5),
    "normal": Level("Vừa", 1.0),
    "loud": Level("To", 1.6),
}

# A scene's own music level, multiplying the video's; a scene without one keeps the video's level.
MUSIC_LEVELS: dict[str, Level] = {
    "off": Level("Tắt nhạc", 0.0),
    "low": Level("Nhạc nhỏ", 0.4),
    "high": Level("Nhạc to", 1.6),
}


@dataclass(frozen=True)
class SceneSound:
    sound: str
    start: float = 0.0  # seconds into its scene
    volume: str = "normal"


def make_sound(name: str, output: Path) -> Path:
    """The sound as an MP3 (stereo), for the studio to play; the render makes it inside its own graph."""
    tools = find_tools()
    argv = [tools.ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", SOUNDS[name].source]
    argv += ["-ac", "2", "-c:a", "libmp3lame", "-b:a", "128k", str(output)]
    run(argv, "FFmpeg không tạo được âm thanh")
    return output
