"""A "Cảnh động": an assistant (Claude through MCP) writes a scene as HTML + GSAP, and the worker renders it with
HyperFrames (Apache-2.0) into a short clip that becomes the scene's clip. FFmpeg still makes the video from it like
any other clip, so the render core does not change.

The markup is untrusted: it is checked here before it is stored (no outside address, no network or timer APIs, no
document-level tags), and the worker's Chrome renders it with every address but this machine sent to a dead proxy:
api/Dockerfile.worker starts HyperFrames' headless Chrome through a wrapper with --proxy-server, and the render's
environment points the proxy variables there too.

`python -m reels_api.motion <folder>` renders a short scene, as the worker image's build does to prove that
its Chrome starts.
"""

import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .clips import check_clip
from .errors import ApiError
from .models import Job, Scene, Video
from .script_rules import CROSSFADE_SIDE_SECONDS
from .storage import DirectoryStorage
from .uploads import UploadRejected
from .videos import new_key, refresh_thumbnail, split_scenes

log = logging.getLogger(__name__)

WIDTH, HEIGHT, FPS = 1080, 1920, 30
MIN_SECONDS, MAX_SECONDS = 1.0, 10.0
MAX_MARKUP = 100_000  # characters; a photo the markup needs comes as assets/photo.*, not inlined
RENDER_SECONDS = 10 * 60  # under the worker's job limit, so a stuck render fails with its own message
# A little more than the scene, so the clip never ends on a held frame (as reference.py cuts clips).
SPARE_SECONDS = 0.2
# Chrome sends every address except this machine (HyperFrames' own file server) here, where nothing listens.
DEAD_PROXY = "http://127.0.0.1:9"

# (pattern, why it is refused). Case-insensitive. Each names what the assistant should do instead.
_REFUSED = [
    (
        r"<\s*/?\s*(!doctype|html|head|body|iframe|frame|frameset|object|embed|link|meta|base|form|portal)\b",
        "Chỉ viết phần tử bên trong khung cảnh (div, img, svg, style, script), không viết html/head/body, "
        "iframe, link, meta hay form",
    ),
    (r"<\s*script\b[^>]*\bsrc\s*=", "Không nạp script từ file khác; GSAP đã có sẵn"),
    (
        r"\b(https?|ftp|wss?|file|blob|javascript)\s*:",
        "Không dùng địa chỉ ngoài; ảnh của cảnh có ở assets/photo, ảnh khác thì nhúng data:",
    ),
    (r"(src|href|srcset|poster|xlink:href)\s*=\s*[\"']?\s*//|url\(\s*[\"']?\s*//", "Không dùng địa chỉ ngoài"),
    (r"@import\b", "Không dùng @import; viết CSS ngay trong thẻ style"),
    (
        r"\b(fetch|importScripts|eval|setTimeout|setInterval|requestAnimationFrame)\s*\(|\bimport\s*\(",
        "Không gọi mạng, eval hay hẹn giờ; mọi chuyển động thêm vào timeline tl",
    ),
    (
        r"\b(XMLHttpRequest|WebSocket|EventSource|sendBeacon|SharedWorker|serviceWorker|RTCPeerConnection|"
        r"localStorage|sessionStorage|indexedDB|document\.cookie|window\.open|new\s+Function|new\s+Worker)\b",
        "Không dùng mạng, bộ nhớ trình duyệt hay cửa sổ mới",
    ),
    (r"\blocation\s*(\.\s*(href|assign|replace)|=)", "Không chuyển trang"),
    (
        r"\b(Date\.now|performance\.now|Math\.random)\b|new\s+Date\s*\(\s*\)",
        "Không dùng giờ hệ thống hay số ngẫu nhiên: mỗi lần render phải ra cùng một hình",
    ),
]
_REFUSED_RE = [(re.compile(pattern, re.IGNORECASE), why) for pattern, why in _REFUSED]


class MotionError(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message, self.detail = message, detail


def check_markup(raw: str) -> str:
    """The markup as stored, or ApiError 422 saying what to change."""
    markup = unicodedata.normalize("NFC", raw or "").replace("\r\n", "\n").strip()
    if not markup:
        raise ApiError(422, "invalid_motion", "Hãy viết HTML cho cảnh động")
    if len(markup) > MAX_MARKUP:
        raise ApiError(422, "invalid_motion", f"HTML cảnh động dài quá {MAX_MARKUP:,} ký tự".replace(",", "."))
    for pattern, why in _REFUSED_RE:
        found = pattern.search(markup)
        if found:
            raise ApiError(422, "invalid_motion", f"{why} (gặp “{found.group(0).strip()[:40]}”)")
    return markup


def check_seconds(seconds: float) -> float:
    if not math.isfinite(seconds) or not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise ApiError(422, "invalid_motion", f"Cảnh động dài từ {MIN_SECONDS:g} đến {MAX_SECONDS:g} giây")
    return round(seconds, 1)


def request(db: DbSession, storage: DirectoryStorage, scene_id: int, markup: str, seconds: float, me) -> dict:
    """Store the markup and queue the job that renders it (one active job per video, like every job)."""
    # The editor's locks, payload and queue live with its routes; imported here so the worker loads no web layer.
    from . import routes_videos
    from .videos import ensure_unlocked, lock_scene

    markup, seconds = check_markup(markup), check_seconds(seconds)
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    before = scene.motion or {}
    photo_key, stale = before.get("photo_key"), None
    # The scene's photo now (a transparent product photo, say) is what the markup shows as assets/photo.*. It is
    # copied, because the clip the job makes takes the photo's place on the scene.
    if scene.image_key and storage.exists(scene.image_key):
        stale = photo_key
        photo_key = new_key(video.id, f"motion-photo-{scene.id}", scene.image_key.rsplit(".", 1)[-1])
        storage.save_file(photo_key, storage.path(scene.image_key))
    scene.motion = {
        "html": markup,
        "seconds": seconds,
        "photo_key": photo_key,
        "clip_key": before.get("clip_key"),
        "pending": True,
    }
    routes_videos._enqueue(db, video, "motion", me, scene_id=scene.id)
    payload = routes_videos._saved(db, video)
    storage.delete(stale)
    return payload


def find_tools() -> tuple[str, Path]:
    """The HyperFrames CLI on PATH and the GSAP installed beside it (api/Dockerfile.worker installs both)."""
    cli = shutil.which("hyperframes")
    if cli is None:
        raise MotionError("Máy chủ chưa cài HyperFrames nên chưa làm được cảnh động", "hyperframes not on PATH")
    for folder in Path(cli).resolve().parents:
        gsap = folder / "node_modules" / "gsap" / "dist" / "gsap.min.js"
        if gsap.is_file():
            return cli, gsap
    raise MotionError("Máy chủ chưa cài GSAP cho HyperFrames", f"no node_modules/gsap beside {cli}")


def composition(markup: str, seconds: float, photo: str | None) -> str:
    """The HyperFrames project's index.html: a 1080×1920 root of `seconds`, a paused GSAP timeline `tl` the markup
    adds its motion to, the template's font, and the markup inside the root."""
    from reels_render.textbox import FONT_PATH

    photo_note = f"<!-- Ảnh của cảnh: assets/{photo} -->" if photo else ""
    return f"""<!doctype html>
<html lang="vi">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={WIDTH}, height={HEIGHT}" />
    <script src="assets/gsap.min.js"></script>
    <style>
      @font-face {{ font-family: "Be Vietnam Pro"; src: url("assets/{FONT_PATH.name}"); font-weight: 100 900; }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {WIDTH}px; height: {HEIGHT}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: {WIDTH}px; height: {HEIGHT}px; overflow: hidden;
        font-family: "Be Vietnam Pro", sans-serif; color: #fff; }}
    </style>
    <script>const tl = gsap.timeline({{ paused: true }});</script>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{seconds:g}"
      data-width="{WIDTH}" data-height="{HEIGHT}">
{photo_note}
{markup}
    </div>
    <script>window.__timelines["main"] = tl; tl.seek(0);</script>
  </body>
</html>
"""


def _env() -> dict:
    env = dict(os.environ)
    quiet = ("HYPERFRAMES_NO_UPDATE_CHECK", "HYPERFRAMES_NO_TELEMETRY", "DO_NOT_TRACK", "HYPERFRAMES_SKIP_SKILLS")
    env.update({name: "1" for name in quiet})
    env.update(HYPERFRAMES_NO_OPTIONAL_INSTALL="1", PRODUCER_LOW_MEMORY_MODE="true")
    for name in ("http_proxy", "https_proxy", "all_proxy"):
        env[name] = env[name.upper()] = DEAD_PROXY
    env["no_proxy"] = env["NO_PROXY"] = "localhost,127.0.0.1,::1"
    return env


def render_clip(folder: Path, markup: str, seconds: float, photo: Path | None) -> Path:
    """Write the project in `folder` and render it to folder/motion.mp4."""
    from reels_render.textbox import FONT_PATH

    cli, gsap = find_tools()
    project = folder / "project"
    assets = project / "assets"
    assets.mkdir(parents=True)
    shutil.copyfile(gsap, assets / "gsap.min.js")
    shutil.copyfile(FONT_PATH, assets / FONT_PATH.name)
    name = None
    if photo is not None:
        name = "photo" + photo.suffix.lower()
        shutil.copyfile(photo, assets / name)
    (project / "index.html").write_text(composition(markup, seconds, name), encoding="utf-8")
    target = folder / "motion.mp4"
    argv = [cli, "render", "--output", str(target), "--fps", str(FPS), "--workers", "1", "--no-browser-gpu"]
    try:
        done = subprocess.run(
            argv, cwd=project, env=_env(), capture_output=True, text=True, timeout=RENDER_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        raise MotionError(f"HyperFrames render quá {RENDER_SECONDS // 60} phút nên đã dừng") from None
    if done.returncode != 0 or not target.is_file():
        tail = (done.stderr or done.stdout or "")[-3000:]
        raise MotionError("HyperFrames không render được cảnh động, hãy sửa HTML rồi thử lại", tail)
    return target


def run(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    """The motion job: render the scene's markup and make the clip the scene's clip."""
    scene = db.get(Scene, job.scene_id)
    if scene is None or not scene.motion:
        raise MotionError("Cảnh không còn hoặc không có cảnh động")
    motion = dict(scene.motion)
    sides = 1 if scene.is_title else 2
    length = round(motion["seconds"] + sides * CROSSFADE_SIDE_SECONDS + SPARE_SECONDS, 2)
    photo_key = motion.get("photo_key")
    with tempfile.TemporaryDirectory(prefix="reels_motion_") as raw:
        folder = Path(raw)
        photo = storage.path(photo_key) if photo_key and storage.exists(photo_key) else None
        from . import render_nodes

        if render_nodes.enabled(db):
            # A member's render machine runs HyperFrames; the api attaches its clip with `attach`.
            bundle = folder / "bundle"
            bundle.mkdir()
            name = None
            if photo is not None:
                name = "photo" + photo.suffix.lower()
                shutil.copyfile(photo, bundle / name)
            manifest = {"kind": "motion", "html": motion["html"], "seconds": length, "photo": name}
            render_nodes.pack(db, storage, job, manifest, bundle)
            raise render_nodes.HandedOff
        target = render_clip(folder, motion["html"], length, photo)
        attach(db, storage, job, target)


def attach(db: DbSession, storage: DirectoryStorage, job: Job, target: Path) -> None:
    """The rendered clip becomes the scene's clip; the worker's own render and a render machine's both end here."""
    scene = db.get(Scene, job.scene_id)
    if scene is None or not scene.motion:
        raise MotionError("Cảnh không còn hoặc không có cảnh động")
    motion = dict(scene.motion)
    photo_key = motion.get("photo_key")
    try:
        clip = check_clip(target)
    except UploadRejected as err:
        raise MotionError("HyperFrames làm ra clip không dùng được", str(err)) from None
    video = db.scalar(select(Video).where(Video.id == scene.video_id).with_for_update())
    db.refresh(scene)
    old = [key for key in (scene.image_key, scene.video_key) if key and key != photo_key]
    key = new_key(video.id, f"motion-{scene.id}", clip.extension)
    storage.save_file(key, target)
    scene.video_key, scene.video_seconds, scene.video_start, scene.video_speed = key, round(clip.seconds, 3), 0, 1
    # A new or removed clip has no sound of its own heard, nor words ("Edit từ footage").
    scene.video_sound, scene.words = False, None
    scene.image_key, scene.image_source, scene.image_error, scene.image_auto = None, None, None, False
    # The motion is timed to its seconds, so the scene keeps them rather than following the narration.
    scene.seconds, scene.seconds_auto = motion["seconds"], False
    scene.motion = {**motion, "clip_key": key, "pending": False}
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    db.commit()
    for stale in old:
        storage.delete(stale)
    log.info("Scene %s: motion clip %s (%.1fs)", scene.id, key, clip.seconds)


def fail_pending(db: DbSession, job: Job) -> None:
    """A failed motion job leaves the scene as it was, with the markup kept for the assistant to fix."""
    scene = db.get(Scene, job.scene_id) if job.scene_id else None
    if scene is not None and scene.motion and scene.motion.get("pending"):
        scene.motion = {**scene.motion, "pending": False}
        db.commit()


if __name__ == "__main__":
    import sys

    made = render_clip(Path(sys.argv[1]), '<div id="t" style="font-size:96px">Cảnh động</div>', 1.5, None)
    print(f"motion check: {check_clip(made).seconds:.2f}s")
