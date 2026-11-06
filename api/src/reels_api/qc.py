"""Automatic QC of a rendered MP4, run by the render job before the MP4 is saved (videos.qc).

The checks and thresholds follow the platforms' delivery specs, as AIEV's QC does (github.com/notivn/AIEVv2,
apps/server/src/qc.ts, MIT): TikTok, Reels and Shorts play back at about -14 LUFS, want true peaks at or under
-1 dBTP, and a viewer scrolls away from black frames, frozen pictures and dead air. Every check is pass, warn or fail
with a Vietnamese reason; the video's status is its worst check. QC never fails the render: a measurement that
cannot be made is a warning saying so.
"""

import logging
import re
import subprocess
from pathlib import Path

from reels_render.ffmpeg import find_tools, probe

log = logging.getLogger(__name__)

WIDTH, HEIGHT, FPS = 1080, 1920, 30
TARGET_LUFS = -14.0
LUFS_WARN, LUFS_FAIL = 2.0, 4.0  # LU away from the target
PEAK_WARN, PEAK_FAIL = -1.0, -0.5  # dBTP
SILENT_LUFS = -70.0  # EBU R128's gate: quieter is no sound at all
BLACK_MIN, BLACK_FAIL = 0.25, 1.0  # seconds
EDGE = 0.3  # a black frame this close to the start or the end is a fade, not a fault
FREEZE_MIN = 2.0
DEAD_AIR_DB, DEAD_AIR_MIN = -45, 1.5
TAIL_SILENCE_WARN = 1.2
SHORT, LONG, TOO_SHORT = 20.0, 40.0, 5.0  # the channel's 20–40 s; under 5 s is not a video
TIMEOUT = 120
RANK = {"pass": 0, "warn": 1, "fail": 2}


def _check(key: str, label: str, status: str, detail: str) -> dict:
    return {"id": key, "label": label, "status": status, "detail": detail}


def _ffmpeg_log(args: list[str]) -> str:
    tools = find_tools()
    done = subprocess.run(
        [tools.ffmpeg, "-hide_banner", "-nostats", "-nostdin", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr[-500:])
    return done.stderr


def _spans(text: str, start: str, end: str) -> list[tuple[float, float]]:
    """(start, end) pairs of a detect filter's log, an open span ending at the end of the file (inf)."""
    starts = [float(value) for value in re.findall(rf"{start}:\s*(-?[\d.]+)", text)]
    ends = [float(value) for value in re.findall(rf"{end}:\s*(-?[\d.]+)", text)]
    return [(begin, ends[index] if index < len(ends) else float("inf")) for index, begin in enumerate(starts)]


def _times(spans: list[tuple[float, float]], length: float) -> str:
    return ", ".join(f"{begin:.1f}–{min(end, length):.1f}s" for begin, end in spans[:5])


def check_format(info: dict) -> tuple[list[dict], float]:
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    length = float(info.get("format", {}).get("duration") or 0)
    size = (video.get("width"), video.get("height"))
    num, _, den = str(video.get("avg_frame_rate", "0/1")).partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    checks = []
    if size != (WIDTH, HEIGHT) or video.get("codec_name") != "h264":
        checks.append(
            _check(
                "format",
                "Định dạng",
                "fail",
                f"{size[0]}×{size[1]} {video.get('codec_name')}, cần 1080×1920 H.264",
            )
        )
    elif abs(fps - FPS) > 0.5:
        checks.append(_check("format", "Định dạng", "warn", f"{fps:.2f} khung/giây, cần {FPS}"))
    else:
        checks.append(_check("format", "Định dạng", "pass", f"1080×1920 H.264, {fps:.0f} khung/giây"))
    if audio is None:
        checks.append(_check("audio_track", "Âm thanh", "fail", "MP4 không có đường tiếng"))
    if length < TOO_SHORT:
        checks.append(_check("duration", "Độ dài", "fail", f"{length:.1f} giây, quá ngắn"))
    elif length < SHORT or length > LONG:
        checks.append(_check("duration", "Độ dài", "warn", f"{length:.1f} giây, kênh nhắm 20–40 giây"))
    else:
        checks.append(_check("duration", "Độ dài", "pass", f"{length:.1f} giây"))
    return checks, length


def check_audio(path: Path, length: float, expect_sound: bool) -> list[dict]:
    text = _ffmpeg_log(
        [
            "-i",
            str(path),
            "-vn",
            "-af",
            f"ebur128=peak=true,silencedetect=noise={DEAD_AIR_DB}dB:d={DEAD_AIR_MIN}",
            "-f",
            "null",
            "-",
        ]
    )
    summary = text[text.rfind("Summary:") :] if "Summary:" in text else ""
    loudness = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", summary)
    peak = re.search(r"True peak:\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS", summary)
    lufs = float(loudness.group(1)) if loudness and loudness.group(1) != "-inf" else float("-inf")
    checks = []
    if lufs <= SILENT_LUFS:
        status = "fail" if expect_sound else "warn"
        return [_check("loudness", "Âm lượng", status, "Video không có tiếng")]
    off = lufs - TARGET_LUFS
    status = "fail" if abs(off) > LUFS_FAIL else "warn" if abs(off) > LUFS_WARN else "pass"
    hint = "" if status == "pass" else (" (to quá, nền tảng sẽ kéo nhỏ)" if off > 0 else " (nhỏ quá)")
    checks.append(_check("loudness", "Âm lượng", status, f"{lufs:.1f} LUFS, chuẩn −14{hint}"))
    if peak and peak.group(1) != "-inf":
        top = float(peak.group(1))
        status = "fail" if top > PEAK_FAIL else "warn" if top > PEAK_WARN else "pass"
        checks.append(_check("true_peak", "Đỉnh tiếng", status, f"{top:.1f} dBTP, tối đa −1"))
    silences = _spans(text, "silence_start", "silence_end")
    tail = [(begin, end) for begin, end in silences if min(end, length) >= length - 0.1 and begin < length]
    inside = [(begin, end) for begin, end in silences if (begin, end) not in tail]
    if tail and length - tail[0][0] > TAIL_SILENCE_WARN:
        checks.append(_check("tail_silence", "Im lặng cuối video", "warn", f"{length - tail[0][0]:.1f} giây cuối"))
    if inside:
        checks.append(_check("dead_air", "Khoảng lặng", "warn", f"Không có tiếng ở {_times(inside, length)}"))
    return checks


def check_picture(path: Path, length: float) -> list[dict]:
    text = _ffmpeg_log(
        [
            "-i",
            str(path),
            "-an",
            "-vf",
            f"blackdetect=d={BLACK_MIN}:pix_th=0.10,freezedetect=n=0.003:d={FREEZE_MIN}",
            "-f",
            "null",
            "-",
        ]
    )
    black = [
        (begin, end)
        for begin, end in _spans(text, "black_start", "black_end")
        if begin > EDGE and min(end, length) < length - EDGE
    ]
    freeze = _spans(text, "freeze_start", "freeze_end")
    checks = []
    if black:
        worst = max(min(end, length) - begin for begin, end in black)
        status = "fail" if worst >= BLACK_FAIL else "warn"
        checks.append(_check("black", "Khung đen", status, f"Màn hình đen ở {_times(black, length)}"))
    else:
        checks.append(_check("black", "Khung đen", "pass", "Không có"))
    if freeze:
        checks.append(_check("freeze", "Đứng hình", "warn", f"Hình đứng yên ở {_times(freeze, length)}"))
    else:
        checks.append(_check("freeze", "Đứng hình", "pass", "Không có"))
    return checks


def measure(path: Path, expect_sound: bool) -> dict:
    """{"status", "checks": [...]} for the MP4 at `path`."""
    checks: list[dict] = []
    try:
        found, length = check_format(probe(find_tools().ffprobe, path))
        checks += found
    except Exception as err:  # QC reports what it could not measure instead of failing the render
        log.warning("QC could not read %s: %s", path, err)
        return {"status": "warn", "checks": [_check("read", "Đọc MP4", "warn", "Không đọc được MP4 để kiểm tra")]}
    for label, step in (
        ("Âm thanh", lambda: check_audio(path, length, expect_sound)),
        ("Hình ảnh", lambda: check_picture(path, length)),
    ):
        try:
            checks += step()
        except Exception as err:  # as above: one measurement failing leaves the others
            log.warning("QC %s failed for %s: %s", label, path, err)
            checks.append(_check("measure", label, "warn", f"Không đo được {label.lower()}"))
    status = max((check["status"] for check in checks), key=RANK.__getitem__, default="pass")
    return {"status": status, "checks": checks}
