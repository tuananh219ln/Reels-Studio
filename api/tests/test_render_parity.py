"""The server render (rows in Postgres, photos in storage) gives the same MP4 as the CLI on the sample."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from conftest import API_DIR
from reels_api.frames import compose_frame
from reels_api.models import Scene, Video
from reels_api.storage import DirectoryStorage
from reels_render.timeline import FPS, build_timeline
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import jobs

SAMPLE = API_DIR.parent / "samples" / "xuong-khop.json"
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe không có trên PATH")


def probe(path: Path) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def frame(video: Path, seconds: float, target: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{seconds:.3f}", "-i", str(video), "-frames:v", "1",
                    str(target)], check=True)
    return Image.open(target).convert("RGB")


def mean_difference(a: Image.Image, b: Image.Image) -> float:
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def load_sample(factory, storage: DirectoryStorage, user) -> int:
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with factory() as db:
        video = Video(topic="xương khớp", has_script=True, created_by_id=user.id)
        db.add(video)
        db.flush()
        for position, item in enumerate([data["title"], *data["scenes"]]):
            image = SAMPLE.parent / item["image"]
            key = f"videos/{video.id}/sample-{position}{image.suffix}"
            storage.save_file(key, image)
            db.add(Scene(video_id=video.id, is_title=position == 0, position=position, text=item["text"],
                         seconds=item["seconds"], keywords=item.get("keywords", []), image_key=key,
                         image_source="upload"))
        db.commit()
        return video.id


def test_server_render_matches_the_cli_and_the_title_preview(committed, tmp_path):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    video_id = load_sample(committed, storage, user)

    job_id = add_job(committed, video_id, user.id, kind="render", status="running")
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert job.status == "done", job.error
    with committed() as db:
        video = db.get(Video, video_id)
        server_mp4 = storage.path(video.mp4_key)
        title = next(scene for scene in video.scenes if scene.is_title)
        title_image, title_text = storage.path(title.image_key), title.text
        print(f"render took {video.render_seconds}s for {video.mp4_seconds}s of video")

    cli_mp4 = tmp_path / "cli.mp4"
    subprocess.run([sys.executable, "-m", "reels_render", str(SAMPLE), "-o", str(cli_mp4)], check=True,
                   stdin=subprocess.DEVNULL, capture_output=True)

    server, cli = probe(server_mp4), probe(cli_mp4)
    assert float(server["format"]["duration"]) == pytest.approx(float(cli["format"]["duration"]), abs=1 / FPS)
    for info in (server, cli):
        stream = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert (stream["width"], stream["height"]) == (1080, 1920)

    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    timeline = build_timeline([item["seconds"] for item in [data["title"], *data["scenes"]]])
    start = 0
    for index, frames in enumerate(timeline.scene_frames):
        middle = (start + frames / 2) / FPS
        start += frames
        a = frame(server_mp4, middle, tmp_path / f"server-{index}.png")
        b = frame(cli_mp4, middle, tmp_path / f"cli-{index}.png")
        assert mean_difference(a, b) <= 3, f"scene {index}"

    first = frame(server_mp4, 0, tmp_path / "first.png")
    assert mean_difference(first, compose_frame(title_image, title_text, is_title=True)) <= 3
