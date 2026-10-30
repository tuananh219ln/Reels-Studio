"""Local stand-ins for the Claude Messages API, the Pixabay API and ElevenLabs TTS, for pytest and E2E.

The app reaches them only through ANTHROPIC_BASE_URL, PIXABAY_API_URL and ELEVENLABS_API_URL, so production
code has no test switches. Run `python fake_services.py <port>` for E2E; pytest starts FakeServices in a thread.
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
                body = json.loads(self.rfile.read(length) or b"{}")
                path = urllib.parse.urlsplit(self.path).path
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
    print(f"Fake Claude/Pixabay/ElevenLabs on {services.url}", flush=True)
    services.server.serve_forever()
