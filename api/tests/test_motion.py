"""A "Cảnh động" (motion.py): the markup checks, the MCP tool that queues it, and the job that renders it through a
fake HyperFrames CLI on PATH (the real one needs Node and Chrome; api/Dockerfile.worker checks it at build time)."""

import json
import os
import sys
from types import SimpleNamespace

import pytest
from conftest import make_video, needs_ffmpeg
from sqlalchemy import select
from test_mcp import call, grant, mcp_client  # noqa: F401  (mcp_client is a fixture)
from worker_helpers import add_user, committed, job_row  # noqa: F401  (committed is a fixture)

from reels_api import jobs, motion
from reels_api.errors import ApiError
from reels_api.models import Job, Scene
from reels_api.script_rules import CROSSFADE_SIDE_SECONDS
from reels_api.videos import motion_payload

GOOD = """<img class="sp" src="assets/photo.jpg" style="position:absolute;top:500px;left:140px;width:800px">
<div class="gia" style="position:absolute;bottom:300px;width:100%;text-align:center;font-size:140px">899K</div>
<script>tl.from(".sp", {y: 400, opacity: 0, duration: 0.6}, 0).from(".gia", {scale: 0, duration: 0.4}, 0.5);</script>"""

FAKE_CLI = """import json, os, re, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("--output") + 1])
html = Path("index.html").read_text(encoding="utf-8")
Path(os.environ["FAKE_HF_REPORT"]).write_text(json.dumps({
    "args": args, "html": html, "assets": sorted(os.listdir("assets")),
    "https_proxy": os.environ.get("https_proxy"), "no_proxy": os.environ.get("no_proxy"),
}), encoding="utf-8")
if os.environ.get("FAKE_HF_FAIL"):
    print("Error: SyntaxError: Unexpected token in composition", file=sys.stderr)
    sys.exit(1)
seconds = re.search(r'data-duration="([0-9.]+)"', html).group(1)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
    f"testsrc=size=1080x1920:rate=30:duration={seconds}", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(out)],
    check=True)
"""


@pytest.fixture
def fake_hyperframes(tmp_path, monkeypatch):
    """`hyperframes` on PATH with node_modules/gsap beside it, like the worker image's /opt/hyperframes."""
    root = tmp_path / "hf"
    (root / "bin").mkdir(parents=True)
    (root / "node_modules" / "gsap" / "dist").mkdir(parents=True)
    (root / "node_modules" / "gsap" / "dist" / "gsap.min.js").write_text("/* gsap */", encoding="utf-8")
    cli = root / "bin" / "hyperframes"
    cli.write_text(f"#!{sys.executable}\n{FAKE_CLI}", encoding="utf-8")
    cli.chmod(0o755)
    monkeypatch.setenv("PATH", f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}")
    report = tmp_path / "report.json"
    monkeypatch.setenv("FAKE_HF_REPORT", str(report))
    return report


needs_posix = pytest.mark.skipif(os.name == "nt", reason="the fake CLI is a script with a shebang")


# --- The markup checks ---


@pytest.mark.parametrize(
    "markup",
    [
        "<html><body>x</body></html>",
        '<iframe src="x"></iframe>',
        '<script src="assets/x.js"></script>',
        '<img src="https://evil.example/a.png">',
        "<div style=\"background:url('//evil.example/a.png')\"></div>",
        "<style>@import 'x.css';</style>",
        "<script>fetch('/api/videos')</script>",
        "<script>new WebSocket('ws://x')</script>",
        "<script>setTimeout(() => {}, 10)</script>",
        "<script>tl.to('.a', {x: Math.random() * 100})</script>",
        "<script>location.href = 'x'</script>",
        "<script>document.cookie</script>",
        '<a href="javascript:alert(1)">x</a>',
        "",
        "x" * (motion.MAX_MARKUP + 1),
    ],
)
def test_markup_that_could_reach_out_or_change_between_renders_is_refused(markup):
    with pytest.raises(ApiError) as refused:
        motion.check_markup(markup)
    assert refused.value.status == 422 and refused.value.message


def test_good_markup_is_kept_and_the_composition_wraps_it():
    assert motion.check_markup(f"  {GOOD}\r\n") == GOOD
    page = motion.composition(GOOD, 3.4, "photo.jpg")
    assert 'data-duration="3.4"' in page and 'data-width="1080"' in page and 'data-height="1920"' in page
    assert '<script src="assets/gsap.min.js"></script>' in page
    assert "const tl = gsap.timeline({ paused: true });" in page and 'window.__timelines["main"] = tl;' in page
    assert GOOD in page and "assets/photo.jpg" in page
    for bad in (0.5, 10.5, float("nan")):
        with pytest.raises(ApiError):
            motion.check_seconds(bad)


def test_the_scene_shows_its_motion_only_while_its_clip_is_the_one_made():
    made = {"html": GOOD, "seconds": 3.0, "photo_key": None, "clip_key": "videos/1/motion-1-a.mp4", "pending": False}
    assert motion_payload(Scene(motion=made, video_key="videos/1/motion-1-a.mp4"))["seconds"] == 3.0
    assert motion_payload(Scene(motion=made, video_key="videos/1/clip-1-b.mp4")) is None
    assert motion_payload(Scene(motion={**made, "pending": True}, video_key=None))["pending"] is True
    assert motion_payload(Scene(motion=None, video_key=None)) is None


# --- The job, in process on committed rows ---


def queue(factory, storage, seconds=3.0):
    user = add_user(factory)
    with factory() as db:
        video = make_video(db, storage, user)
        scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).limit(1))
        photo = scene.image_key
        motion.request(db, storage, scene.id, GOOD, seconds, SimpleNamespace(user_id=user.id))
        job = db.scalar(select(Job).where(Job.video_id == video.id))
        assert (job.kind, job.status, job.scene_id) == ("motion", "queued", scene.id)
        job.status = "running"
        db.commit()
        return job.id, scene.id, photo


@needs_ffmpeg
@needs_posix
def test_the_job_renders_the_markup_into_the_scenes_clip(committed, storage, fake_hyperframes):  # noqa: F811
    job_id, scene_id, photo = queue(committed, storage)
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert job.status == "done", (job.error, job.error_detail)
    with committed() as db:
        scene = db.get(Scene, scene_id)
        assert scene.video_key == scene.motion["clip_key"] and storage.exists(scene.video_key)
        assert scene.image_key is None and not storage.exists(photo)  # the clip took the photo's place
        assert storage.exists(scene.motion["photo_key"])  # the copy the markup shows stays for a later change
        assert (scene.seconds, scene.seconds_auto, scene.motion["pending"]) == (3.0, False, False)
        assert motion_payload(scene) == {"html": GOOD, "seconds": 3.0, "pending": False}
    report = json.loads(fake_hyperframes.read_text(encoding="utf-8"))
    assert report["assets"] == ["BeVietnamPro-Black.ttf", "gsap.min.js", "photo.jpg"]
    assert f'data-duration="{round(3.0 + 2 * CROSSFADE_SIDE_SECONDS + motion.SPARE_SECONDS, 2):g}"' in report["html"]
    assert GOOD in report["html"]
    assert report["https_proxy"] == motion.DEAD_PROXY and "127.0.0.1" in report["no_proxy"]
    assert report["args"][:3] == ["render", "--output", report["args"][2]] and "--no-browser-gpu" in report["args"]


@needs_posix
def test_a_failed_render_keeps_the_scenes_photo_and_says_to_fix_the_html(
    committed,  # noqa: F811
    storage,
    fake_hyperframes,
    monkeypatch,
):
    monkeypatch.setenv("FAKE_HF_FAIL", "1")
    job_id, scene_id, photo = queue(committed, storage)
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert job.status == "failed" and "sửa HTML" in job.error and "SyntaxError" in job.error_detail
    with committed() as db:
        scene = db.get(Scene, scene_id)
        assert scene.image_key == photo and storage.exists(photo) and scene.video_key is None
        assert scene.motion["pending"] is False and motion_payload(scene) is None


def test_without_hyperframes_the_job_says_the_server_lacks_it(committed, storage, monkeypatch):  # noqa: F811
    which = motion.shutil.which
    monkeypatch.setattr(
        motion.shutil, "which", lambda name, *args, **kw: None if name == "hyperframes" else which(name)
    )
    job_id, _, _ = queue(committed, storage)
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert job.status == "failed" and "chưa cài HyperFrames" in job.error


# --- The MCP tool ---


def test_the_assistant_queues_a_motion_scene_and_cannot_queue_a_second_meanwhile(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).limit(1))
    refused = call(mcp_client, token, "set_scene_motion", scene_id=scene.id, html="<iframe></iframe>", seconds=3)
    assert refused["isError"]
    assert db.scalar(select(Job.id).where(Job.video_id == video.id)) is None
    made = call(mcp_client, token, "set_scene_motion", scene_id=scene.id, html=GOOD, seconds=3)
    assert not made.get("isError"), made
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert (job.kind, job.status, job.scene_id, job.created_by_id) == ("motion", "queued", scene.id, user.id)
    db.refresh(scene)
    assert scene.motion["html"] == GOOD and scene.motion["pending"] is True
    assert storage.exists(scene.motion["photo_key"]) and scene.image_key  # the photo stays until the clip is made
    again = call(mcp_client, token, "set_scene_motion", scene_id=scene.id, html=GOOD, seconds=3)
    assert again["isError"]
