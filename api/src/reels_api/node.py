"""`python -m reels_api node`: a member's computer renders the team's jobs (render_nodes.py).

It asks the api for a job every few seconds with its token, downloads the job's bundle, renders it with this
computer's FFmpeg (and HyperFrames for a motion scene), measures QC, uploads the MP4 and says it is done. It never
touches the database or the storage itself, only /api/node/... over HTTPS. A lost connection is retried; a render
that fails is reported with FFmpeg's or HyperFrames' reason, so the job fails on the video page as any other.

Set REELS_SERVER (the web address, e.g. https://reels.example.com) and REELS_NODE_TOKEN (shown once when the machine
is added on Cài đặt › Máy render), or pass --server and --token.
"""

import json
import logging
import os
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

log = logging.getLogger("reels_api.node")

POLL_SECONDS = 5
RETRY_SECONDS = 15
HEARTBEAT_SECONDS = 30
TIMEOUT = 120


class Client:
    def __init__(self, server: str, token: str):
        self.base = server.rstrip("/") + "/api/node"
        self.headers = {"Authorization": f"Bearer {token}", "User-Agent": "reels-render-node/1"}

    def call(self, method: str, path: str, body=None, content_type: str | None = None, length: int | None = None):
        headers = dict(self.headers)
        if isinstance(body, dict):
            body, content_type = json.dumps(body).encode(), "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        if length is not None:
            headers["Content-Length"] = str(length)
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        return urllib.request.urlopen(request, timeout=TIMEOUT)

    def json(self, method: str, path: str, body=None) -> dict:
        with self.call(method, path, body if body is not None else {} if method != "GET" else None) as answer:
            return json.loads(answer.read() or b"{}")

    def download(self, path: str, target: Path) -> None:
        with self.call("GET", path) as answer, open(target, "wb") as file:
            while chunk := answer.read(1024 * 1024):
                file.write(chunk)

    def upload(self, path: str, source: Path) -> None:
        with open(source, "rb") as file:
            self.call("PUT", path, file, "video/mp4", source.stat().st_size).close()


def _unpack(bundle: Path, folder: Path) -> dict:
    with zipfile.ZipFile(bundle) as archive:
        for name in archive.namelist():
            # The api packs flat files only; anything else is not a bundle it made.
            if "/" in name or "\\" in name or name.startswith("."):
                raise ValueError(f"unexpected file in bundle: {name!r}")
        archive.extractall(folder)
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


def _reason(err: Exception) -> tuple[str, str]:
    """The Vietnamese reason and the technical detail of a render that failed."""
    from reels_render import RenderError
    from reels_render.errors import FFmpegError

    from .motion import MotionError

    if isinstance(err, FFmpegError):
        return "FFmpeg lỗi khi render video (máy render)", err.stderr_tail
    if isinstance(err, MotionError):
        return err.message, err.detail
    if isinstance(err, RenderError):
        return str(err), ""
    return "Máy render gặp lỗi không mong đợi", traceback.format_exc()[-4000:]


def work(client: Client, job_id: int, kind: str) -> None:
    from .render_nodes import render_bundle

    stop = threading.Event()

    def beat():
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                client.json("POST", f"/jobs/{job_id}/heartbeat")
            except (urllib.error.URLError, OSError) as err:
                log.warning("Heartbeat for job %s failed: %s", job_id, err)

    threading.Thread(target=beat, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="reels_node_") as raw:
            folder = Path(raw)
            client.download(f"/jobs/{job_id}/bundle", folder / "bundle.zip")
            work_folder = folder / "bundle"
            manifest = _unpack(folder / "bundle.zip", work_folder)
            log.info("Job %s (%s): rendering", job_id, kind)
            try:
                result = render_bundle(work_folder, manifest)
            except Exception as err:  # every render failure is reported to the api, with its reason
                error, detail = _reason(err)
                log.error("Job %s failed: %s\n%s", job_id, error, detail)
                client.json("POST", f"/jobs/{job_id}/fail", {"error": error, "detail": detail or ""})
                return
            client.upload(f"/jobs/{job_id}/output", work_folder / "output.mp4")
            client.json("POST", f"/jobs/{job_id}/done", result)
            log.info("Job %s done: %.1fs of video in %.1fs", job_id, result["seconds"], result["elapsed"])
    finally:
        stop.set()


def run(server: str, token: str, once: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = Client(server, token)
    log.info("Máy render đang chờ job từ %s (Ctrl+C để dừng)", server)
    while True:
        try:
            job = client.json("POST", "/claim")
            if job.get("job_id"):
                work(client, job["job_id"], job["kind"])
                continue
        except urllib.error.HTTPError as err:
            if err.code == 401:
                log.error("Token sai hoặc máy đã bị xoá trên Cài đặt › Máy render")
                return 1
            log.warning("Máy chủ trả lỗi %s, thử lại sau %ss", err.code, RETRY_SECONDS)
            time.sleep(RETRY_SECONDS)
            continue
        except (urllib.error.URLError, OSError) as err:
            log.warning("Không kết nối được máy chủ (%s), thử lại sau %ss", err, RETRY_SECONDS)
            time.sleep(RETRY_SECONDS)
            continue
        if once:
            return 0
        time.sleep(POLL_SECONDS)


def main(server: str | None, token: str | None, once: bool) -> int:
    server = server or os.environ.get("REELS_SERVER", "")
    token = token or os.environ.get("REELS_NODE_TOKEN", "")
    if not server or not token:
        print("Lỗi: cần REELS_SERVER và REELS_NODE_TOKEN (hoặc --server và --token)")
        return 2
    return run(server, token, once)
