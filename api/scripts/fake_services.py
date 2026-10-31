"""Local stand-ins for the Claude Messages API, Pixabay, ElevenLabs TTS and Facebook Reels, for pytest and E2E.

The app reaches them only through ANTHROPIC_BASE_URL, PIXABAY_API_URL, ELEVENLABS_API_URL and FACEBOOK_API_URL,
so production code has no test switches. Run `python fake_services.py <port>` for E2E; pytest starts FakeServices in a thread.
"""

import hashlib
import io
import json
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

PIXABAY_KEY = "fake-pixabay-key"
ELEVENLABS_KEY = "fake-elevenlabs-key"
FACEBOOK_PAGE = "1234567"
FACEBOOK_TOKEN = "fake-facebook-token"


def script_json(topic: str, seconds: float = 4, scene_count: int = 5) -> dict:
    foods = ["Cá nhỏ", "Sữa chua", "Đậu phụ", "Rau cải", "Vừng đen", "Tôm khô", "Hạnh nhân"]
    return {
        "titles": [f"{n} MÓN TỐT CHO {topic.upper()}"[:60] for n in (5, 6, 7, 4, 3)],
        "title_keywords": ["món ăn giàu canxi"],
        "title_voice": "Mời bạn xem đến cuối nhé",
        "scenes": [
            {"text": f"{food}\nGiàu *canxi*", "seconds": seconds, "voice": f"{food} giàu canxi",
             "keywords": [food.lower(), "món ăn"],
             "image_prompt": f"{food} trên bàn gỗ, ánh sáng tự nhiên"}
            for food in foods[:scene_count]
        ],
        "caption": f"Caption về {topic}. " * 10,
        "hashtags": ["#a", "#b", "#c", "#d", "#e"],
        "affiliates": ["Sữa hạt canxi", "Vừng đen rang"],
        "pinned_comment": "Link sản phẩm ở đây nhé",
        "self_review": ["\"chữa khỏi\" → \"tốt cho\""],
        "music_suggestions": ["Windy Hill", "Morning Coffee"],
    }


class FakeServices:
    def __init__(self, port: int = 0):
        self.lock = threading.Lock()
        self.claude_replies: list[object] = []  # str (raw text) or dict (JSON); empty: a valid script
        self.claude_hang = False
        self.claude_prompts: list[str] = []
        self.pixabay_mode = "ok"  # ok | empty | error500 | hang
        self.pixabay_results: dict[str, list[str]] = {}
        self.pixabay_queries: list[str] = []
        self.image_downloads: list[str] = []
        self.default_seconds = 4.0
        self.tts_mode = "ok"  # ok | quota | error500
        self.tts_ok_count: int | None = None  # with a number, only that many requests succeed, then "quota"
        self.tts_requests: list[dict] = []  # {"voice_id", "text", "model_id", "language_code"}
        self.reels: dict[str, dict] = {}  # video_id -> {"uploaded", "bytes", "finishes", "state", "description", ...}
        self.facebook_finish_fails = 0  # that many finish calls fail: 500 without publishing
        self.facebook_finish_refusals = 0  # that many finish calls are refused: 400 without publishing
        self.facebook_busy_reads = 0  # that many status reads say "processing" before the real status
        self.facebook_empty_status = False  # status reads answer 200 without a status
        self.facebook_finish_replies_lost = 0  # that many finish calls publish, then answer 500
        self.facebook_finish_draft = False  # a finished reel stays in draft, as while Facebook still processes it
        self.facebook_processing = "ok"  # ok | error | rejected (the doc's shape: only the phase says so) | busy
        self.facebook_status_fails = 0  # that many status reads answer 400, as a rate limit may
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self) -> "FakeServices":
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self.claude_hang = False
        self.server.shutdown()
        self.server.server_close()

    def env(self) -> dict[str, str]:
        return {
            "ANTHROPIC_API_KEY": "fake-claude-key",
            "ANTHROPIC_BASE_URL": self.url,
            "PIXABAY_API_KEY": PIXABAY_KEY,
            "PIXABAY_API_URL": f"{self.url}/api/",
            "ELEVENLABS_API_KEY": ELEVENLABS_KEY,
            "ELEVENLABS_API_URL": self.url,
            "FACEBOOK_API_URL": f"{self.url}/facebook",
        }

    def image_url(self, name: str) -> str:
        return f"{self.url}/img/{name}.jpg"

    # --- request handling ---

    def _claude(self, body: dict) -> tuple[int, dict]:
        prompt = body["messages"][-1]["content"]
        with self.lock:
            self.claude_prompts.append(prompt)
            reply = self.claude_replies.pop(0) if self.claude_replies else None
        while self.claude_hang:
            time.sleep(0.2)
        if reply is None:
            topic = prompt.split("Chủ đề: ", 1)[-1].split("\n", 1)[0].strip() or "sức khỏe"
            reply = script_json(topic, self.default_seconds)
        text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return 200, {
            "id": "msg_fake", "type": "message", "role": "assistant", "model": body.get("model", "fake"),
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4},
        }

    def _pixabay(self, query: dict) -> tuple[int, object]:
        keyword = query.get("q", "")
        with self.lock:
            self.pixabay_queries.append(keyword)
        if query.get("key") != PIXABAY_KEY:
            return 400, "[ERROR 400] Invalid or missing API key (https://pixabay.com/api/docs/)."
        if self.pixabay_mode == "error500":
            return 500, "server error"
        if self.pixabay_mode == "hang":
            time.sleep(30)
        if self.pixabay_mode == "empty":
            names = []
        else:
            names = self.pixabay_results.get(keyword) or [
                hashlib.sha1(f"{keyword}-{n}".encode()).hexdigest()[:10] for n in range(1, 4)
            ]
        hits = [{"id": n, "largeImageURL": self.image_url(name), "previewURL": self.image_url(name)}
                for n, name in enumerate(names)]
        return 200, {"total": len(hits), "totalHits": len(hits), "hits": hits}

    def _tts(self, voice_id: str, key: str, body: dict) -> tuple[int, object]:
        with self.lock:
            self.tts_requests.append({"voice_id": voice_id, "text": body.get("text"), "model_id": body.get("model_id"),
                                      "language_code": body.get("language_code")})
        if key != ELEVENLABS_KEY:
            return 401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}
        if self.tts_mode == "quota" or (self.tts_ok_count is not None and len(self.tts_requests) > self.tts_ok_count):
            return 401, {"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota"}}
        if self.tts_mode == "error500":
            return 500, {"detail": "server error"}
        # A tone instead of speech, 0.3 s per word, so tests can tell how long each narration is.
        seconds = 0.3 * max(1, len(str(body.get("text", "")).split()))
        audio = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}",
             "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "-"],
            capture_output=True, check=True,
        ).stdout
        return 200, audio

    def _reels_call(self, page: str, form: dict) -> tuple[int, dict]:
        if form.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        if page != FACEBOOK_PAGE:
            return 400, {"error": {"message": "Unknown page", "code": 100}}
        with self.lock:
            if form.get("upload_phase") == "start":
                video_id = str(len(self.reels) + 1000)
                self.reels[video_id] = {"uploaded": False, "bytes": 0, "finishes": 0, "state": "draft"}
                return 200, {"video_id": video_id, "upload_url": f"{self.url}/facebook-upload/{video_id}"}
            reel = self.reels[form["video_id"]]
            reel["finishes"] += 1
            if self.facebook_finish_refusals:
                self.facebook_finish_refusals -= 1
                return 400, {"error": {"message": "Invalid parameter", "code": 100}}
            if self.facebook_finish_fails:
                self.facebook_finish_fails -= 1
                return 500, {"error": {"message": "Service unavailable", "code": 2}}
            reel["description"] = form.get("description")
            reel["video_state"] = form.get("video_state")
            reel["scheduled_publish_time"] = form.get("scheduled_publish_time")
            if not self.facebook_finish_draft:
                reel["state"] = "scheduled" if form.get("video_state") == "SCHEDULED" else "published"
            if self.facebook_finish_replies_lost:
                self.facebook_finish_replies_lost -= 1
                return 500, {"error": {"message": "Service unavailable", "code": 2}}
        return 200, {"success": True}

    def _reel_status(self, video_id: str, query: dict) -> tuple[int, dict]:
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        with self.lock:
            if self.facebook_status_fails:
                self.facebook_status_fails -= 1
                return 400, {"error": {"message": "Application request limit reached", "code": 4}}
            if self.facebook_empty_status:
                return 200, {"id": video_id}
            busy = self.facebook_busy_reads > 0
            self.facebook_busy_reads -= busy
        reel = self.reels.get(video_id)
        if reel is None or reel.get("lost"):
            return 404, {"error": {"message": "Unknown video", "code": 100}}
        mode = "rejected" if reel.get("rejected") else "busy" if busy else self.facebook_processing
        publishing = {"status": "not_started" if mode == "rejected" else "completed",
                      "publish_status": "draft" if mode == "busy" else reel["state"]}
        if reel.get("scheduled_publish_time"):
            publishing["publish_time"] = int(reel["scheduled_publish_time"])
        return 200, {"id": video_id, "status": {
            "video_status": {"error": "error", "rejected": "processing", "busy": "processing"}.get(mode, "ready"),
            "uploading_phase": {"status": "complete" if reel["uploaded"] else "in_progress"},
            "processing_phase": {
                "error": {"status": "error"},
                "rejected": {"status": "not_started", "error": {"message": "Resolution too low"}},
                "busy": {"status": "in_progress"},
            }.get(mode, {"status": "completed"}),
            "publishing_phase": publishing,
        }}

    def _image(self, name: str) -> bytes:
        with self.lock:
            self.image_downloads.append(name)
        digest = hashlib.sha1(name.encode()).digest()
        buffer = io.BytesIO()
        Image.new("RGB", (720, 1280), (digest[0], digest[1], digest[2])).save(buffer, "JPEG", quality=90)
        return buffer.getvalue()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status: int, body: object, content_type: str = "application/json") -> None:
                data = body if isinstance(body, bytes) else (
                    body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode())
                if isinstance(body, str):
                    content_type = "text/plain; charset=utf-8"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                path = urllib.parse.urlsplit(self.path).path
                if path.startswith("/facebook-upload/"):
                    reel = fake.reels[path.removeprefix("/facebook-upload/")]
                    if self.headers.get("Authorization") != f"OAuth {FACEBOOK_TOKEN}":
                        self._send(401, {"error": {"message": "Invalid OAuth access token", "code": 190}})
                        return
                    reel["uploaded"], reel["bytes"] = True, len(raw)
                    self._send(200, {"success": True})
                    return
                if path.startswith("/facebook/"):
                    form = dict(urllib.parse.parse_qsl(raw.decode()))
                    self._send(*fake._reels_call(path.split("/")[2], form))
                    return
                body = json.loads(raw or b"{}")
                if path == "/v1/messages":
                    self._send(*fake._claude(body))
                elif path.startswith("/v1/text-to-speech/"):
                    status, reply = fake._tts(path.removeprefix("/v1/text-to-speech/"), self.headers.get("xi-api-key"),
                                              body)
                    self._send(status, reply, "audio/mpeg" if isinstance(reply, bytes) else "application/json")
                else:
                    self._send(404, {"error": "not found"})

            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                if parts.path == "/health":
                    self._send(200, {"ok": True})
                elif parts.path.startswith("/facebook/"):
                    query = dict(urllib.parse.parse_qsl(parts.query))
                    target = parts.path.removeprefix("/facebook/")
                    if target == FACEBOOK_PAGE and query.get("access_token") == FACEBOOK_TOKEN:
                        self._send(200, {"id": target, "name": "Trang Dưỡng Sinh"})
                    else:
                        self._send(*fake._reel_status(target, query))
                elif parts.path == "/api/":
                    self._send(*fake._pixabay(dict(urllib.parse.parse_qsl(parts.query))))
                elif parts.path.startswith("/img/"):
                    self._send(200, fake._image(parts.path.removeprefix("/img/").removesuffix(".jpg")), "image/jpeg")
                else:
                    self._send(404, {"error": "not found"})

        return Handler


if __name__ == "__main__":
    services = FakeServices(int(sys.argv[1]))
    # E2E videos stay short so the render finishes quickly.
    services.default_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    print(f"Fake Claude/Pixabay/ElevenLabs/Facebook on {services.url}", flush=True)
    services.server.serve_forever()
