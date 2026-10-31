"""Local stand-ins for the Claude Messages API, an OpenAI-compatible chat API, the stock sources (Pixabay, Pexels, Openverse),
ElevenLabs TTS, Gemini image generation and Facebook Reels, for pytest and E2E.

The app reaches them only through ANTHROPIC_BASE_URL, PIXABAY_API_URL, PEXELS_API_URL,
OPENVERSE_API_URL, ELEVENLABS_API_URL, IMAGE_GEN_API_URL and FACEBOOK_API_URL,
so production code has no test switches. The OpenAI-compatible API (at <url>/openai/v1) is reached the way a
member sets any provider up, through its base URL on /settings/ai. Run `python fake_services.py <port>` for E2E; pytest starts FakeServices in a thread.
"""

import base64
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
PEXELS_KEY = "fake-pexels-key"
OPENVERSE_CLIENT_ID = "fake-openverse-client"
OPENVERSE_CLIENT_SECRET = "fake-openverse-secret"
OPENVERSE_TOKEN = "fake-openverse-token"
ELEVENLABS_KEY = "fake-elevenlabs-key"
IMAGE_GEN_KEY = "fake-image-gen-key"
OPENAI_KEY = "fake-openai-key"
OPENAI_MODELS = ["fake-gpt-mini", "models/fake-gemini-flash"]
FACEBOOK_PAGE = "1234567"
FACEBOOK_TOKEN = "fake-facebook-token"  # the Page's own token, the only one that can post
FACEBOOK_USER_TOKEN = "fake-facebook-user-token"  # manages the Page, gets the Page's token from /me/accounts


def script_json(topic: str, seconds: float = 4, scene_count: int = 5) -> dict:
    # (Vietnamese name, English stock term). Tofu's English term is empty on purpose: the suites
    # cover scenes whose script wrote no English terms and must fall back to the Vietnamese ones.
    foods = [
        ("Cá nhỏ", "small fried fish"),
        ("Sữa chua", "yogurt"),
        ("Đậu phụ", ""),
        ("Rau cải", "green vegetables"),
        ("Vừng đen", "black sesame seeds"),
        ("Tôm khô", "dried shrimp"),
        ("Hạnh nhân", "almonds"),
    ]
    return {
        "titles": [f"{n} MÓN TỐT CHO {topic.upper()}"[:60] for n in (5, 6, 7, 4, 3)],
        "title_keywords": ["món ăn giàu canxi"],
        "title_keywords_en": ["calcium rich food"],
        "title_voice": "Mời bạn xem đến cuối nhé",
        "scenes": [
            {
                "text": f"{food}\nGiàu *canxi*",
                "seconds": seconds,
                "voice": f"{food} giàu canxi",
                "keywords": [food.lower(), "món ăn"],
                "keywords_en": [english, "food"] if english else [],
                "image_prompt": f"{food} trên bàn gỗ, ánh sáng tự nhiên",
            }
            for food, english in foods[:scene_count]
        ],
        "caption": f"Caption về {topic}. " * 10,
        "hashtags": ["#a", "#b", "#c", "#d", "#e"],
        "affiliates": ["Sữa hạt canxi", "Vừng đen rang"],
        "pinned_comment": "Link sản phẩm ở đây nhé",
        "self_review": ['"chữa khỏi" → "tốt cho"'],
        "music_suggestions": ["Windy Hill", "Morning Coffee"],
    }


class FakeServices:
    def __init__(self, port: int = 0):
        self.lock = threading.Lock()
        self.claude_replies: list[object] = []  # str (raw text) or dict (JSON); empty: a valid script
        self.claude_hang = False
        self.claude_prompts: list[str] = []
        # The OpenAI-compatible chat shares claude_replies and claude_prompts; these record what only it sees.
        self.chat_requests: list[dict] = []  # {"model", "authorization"}
        self.chat_finish_reason = "stop"
        self.pixabay_mode = "ok"  # ok | empty | error500 | hang
        self.pixabay_results: dict[str, list[str]] = {}
        self.pixabay_queries: list[str] = []
        self.pexels_mode = "ok"  # ok | error500
        self.pexels_results: dict[str, list[str]] = {}
        self.pexels_queries: list[str] = []
        self.openverse_mode = "ok"  # ok | error500
        self.openverse_results: dict[str, list[dict]] = {}  # keyword -> [{"name", "license"}]
        self.openverse_queries: list[str] = []
        self.openverse_token_requests = 0
        self.openverse_authorized: list[bool] = []  # per search: did it carry the fake access token?
        self.image_downloads: list[str] = []
        self.default_seconds = 4.0
        self.tts_mode = "ok"  # ok | quota | error500
        self.tts_ok_count: int | None = None  # with a number, only that many requests succeed, then "quota"
        self.image_gen_mode = "ok"  # ok | quota | error500
        self.image_gen_ok_count: int | None = None  # with a number, only that many requests succeed, then "quota"
        self.image_gen_refused: list[str] = []  # a prompt containing one of these is safety-refused (200, no image)
        self.image_gen_prompts: list[str] = []
        self.tts_requests: list[dict] = []  # {"voice_id", "text", "model_id", "language_code"}
        self.reels: dict[str, dict] = {}  # video_id -> {"uploaded", "bytes", "finishes", "state", "description", ...}
        self.facebook_finish_fails = 0  # that many finish calls fail: 500 without publishing
        self.facebook_finish_refusals = 0  # that many finish calls are refused: 400 without publishing
        self.facebook_busy_reads = 0  # that many status reads say "processing" before the real status
        self.facebook_empty_status = False  # status reads answer 200 without a status
        self.facebook_finish_replies_lost = 0  # that many finish calls publish, then answer 500
        self.facebook_finish_draft = False  # a finished reel stays in draft, as while Facebook still processes it
        # What the user token manages; each Page's access_token is FACEBOOK_TOKEN.
        self.facebook_pages = [{"id": FACEBOOK_PAGE, "name": "Trang Dưỡng Sinh", "tasks": ["CREATE_CONTENT", "MANAGE"]}]
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
            "PEXELS_API_KEY": PEXELS_KEY,
            "PEXELS_API_URL": f"{self.url}/pexels",
            "OPENVERSE_API_URL": f"{self.url}/openverse",
            "OPENVERSE_CLIENT_ID": OPENVERSE_CLIENT_ID,
            "OPENVERSE_CLIENT_SECRET": OPENVERSE_CLIENT_SECRET,
            "ELEVENLABS_API_KEY": ELEVENLABS_KEY,
            "ELEVENLABS_API_URL": self.url,
            "IMAGE_GEN_API_KEY": IMAGE_GEN_KEY,
            "IMAGE_GEN_API_URL": f"{self.url}/gemini",
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
            "id": "msg_fake",
            "type": "message",
            "role": "assistant",
            "model": body.get("model", "fake"),
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4},
        }

    def _chat(self, authorization: str | None, body: dict) -> tuple[int, dict]:
        with self.lock:
            self.chat_requests.append({"model": body.get("model"), "authorization": authorization})
        if authorization != f"Bearer {OPENAI_KEY}":
            return 401, {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}}
        status, message = self._claude(body)
        text = message["content"][0]["text"]
        return status, {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "model": body.get("model", "fake"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": self.chat_finish_reason,
                }
            ],
            "usage": {"prompt_tokens": message["usage"]["input_tokens"], "completion_tokens": len(text) // 4},
        }

    def _models(self, authorization: str | None, anthropic_key: str | None) -> tuple[int, dict]:
        if anthropic_key is not None:
            if anthropic_key != "fake-claude-key":
                return 401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
            ids = ["claude-haiku-5-5", "claude-sonnet-5-5"]
            data = [{"type": "model", "id": i, "display_name": i, "created_at": "2026-01-01T00:00:00Z"} for i in ids]
            return 200, {"data": data, "has_more": False, "first_id": ids[0], "last_id": ids[-1]}
        if authorization != f"Bearer {OPENAI_KEY}":
            return 401, {"error": {"message": "Incorrect API key provided"}}
        return 200, {"object": "list", "data": [{"id": i, "object": "model"} for i in OPENAI_MODELS]}

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
        hits = [
            {"id": n, "largeImageURL": self.image_url(name), "previewURL": self.image_url(name)}
            for n, name in enumerate(names)
        ]
        return 200, {"total": len(hits), "totalHits": len(hits), "hits": hits}

    def _pexels(self, query: dict, key: str | None) -> tuple[int, object]:
        keyword = query.get("query", "")
        with self.lock:
            self.pexels_queries.append(keyword)
        if key != PEXELS_KEY:
            return 401, {"error": "Invalid API key"}
        if self.pexels_mode == "error500":
            return 500, {"error": "server error"}
        names = self.pexels_results.get(keyword) or [
            hashlib.sha1(f"pexels-{keyword}-{n}".encode()).hexdigest()[:10] for n in range(1, 4)
        ]
        sizes = ("original", "large2x", "large", "medium", "small", "tiny")
        photos = [
            {
                "id": n,
                "width": 720,
                "height": 1280,
                "url": f"{self.url}/pexels-photo/{name}",
                "src": {size: self.image_url(name) for size in sizes},
            }
            for n, name in enumerate(names)
        ]
        return 200, {"total_results": len(photos), "page": 1, "per_page": len(photos), "photos": photos}

    def _openverse_token(self, form: dict) -> tuple[int, object]:
        with self.lock:
            self.openverse_token_requests += 1
        if (
            form.get("grant_type") != "client_credentials"
            or form.get("client_id") != OPENVERSE_CLIENT_ID
            or form.get("client_secret") != OPENVERSE_CLIENT_SECRET
        ):
            return 400, {"error": "invalid_client"}
        return 200, {"access_token": OPENVERSE_TOKEN, "token_type": "Bearer", "expires_in": 3600, "scope": "read"}

    def _openverse(self, query: dict, authorized: bool = False) -> tuple[int, object]:
        keyword = query.get("q", "")
        with self.lock:
            self.openverse_queries.append(keyword)
            self.openverse_authorized.append(authorized)
        if self.openverse_mode == "error500":
            return 500, {"detail": "server error"}
        entries = self.openverse_results.get(keyword)
        if entries is None:
            entries = [
                {"name": hashlib.sha1(f"openverse-{keyword}-{n}".encode()).hexdigest()[:10], "license": "cc0"}
                for n in range(1, 4)
            ]
        results = [
            {
                "id": entry["name"],
                "title": entry["name"],
                "url": self.image_url(entry["name"]),
                "thumbnail": self.image_url(entry["name"]),
                "license": entry["license"],
                "foreign_landing_url": f"{self.url}/openverse/{entry['name']}",
                "width": 720,
                "height": 1280,
            }
            for entry in entries
        ]
        return 200, {"result_count": len(results), "page_count": 1, "page": 1, "results": results}

    def _tts(self, voice_id: str, key: str, body: dict) -> tuple[int, object]:
        with self.lock:
            self.tts_requests.append(
                {
                    "voice_id": voice_id,
                    "text": body.get("text"),
                    "model_id": body.get("model_id"),
                    "language_code": body.get("language_code"),
                }
            )
        if key != ELEVENLABS_KEY:
            return 401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}
        if self.tts_mode == "quota" or (self.tts_ok_count is not None and len(self.tts_requests) > self.tts_ok_count):
            return 401, {"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota"}}
        if self.tts_mode == "error500":
            return 500, {"detail": "server error"}
        # A tone instead of speech, 0.3 s per word, so tests can tell how long each narration is.
        seconds = 0.3 * max(1, len(str(body.get("text", "")).split()))
        audio = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=330:duration={seconds}",
                "-ac",
                "1",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "64k",
                "-f",
                "mp3",
                "-",
            ],
            capture_output=True,
            check=True,
        ).stdout
        return 200, audio

    def _image_gen(self, key: str | None, body: dict) -> tuple[int, dict]:
        try:
            prompt = str(body["contents"][0]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError):
            prompt = ""
        with self.lock:
            self.image_gen_prompts.append(prompt)
            calls = len(self.image_gen_prompts)
        if key != IMAGE_GEN_KEY:
            return 401, {
                "error": {"message": "API key not valid. Please pass a valid API key.", "status": "UNAUTHENTICATED"}
            }
        if self.image_gen_mode == "error500":
            return 500, {"error": {"message": "Internal error", "status": "INTERNAL"}}
        if self.image_gen_mode == "quota" or (self.image_gen_ok_count is not None and calls > self.image_gen_ok_count):
            return 429, {
                "error": {
                    "message": "Quota exceeded for quota metric 'GenerateRequests'",
                    "status": "RESOURCE_EXHAUSTED",
                }
            }
        if any(marker in prompt for marker in self.image_gen_refused):
            # Gemini answers a safety refusal with 200 and no candidates, not with an error.
            return 200, {"promptFeedback": {"blockReason": "SAFETY"}}
        digest = hashlib.sha1(prompt.encode()).digest()
        buffer = io.BytesIO()
        Image.new("RGB", (720, 1280), (digest[0], digest[1], digest[2])).save(buffer, "PNG")
        data = base64.b64encode(buffer.getvalue()).decode()
        return 200, {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": data}}]}}]}

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

    def _me(self, path: str, query: dict) -> tuple[int, dict]:
        token = query.get("access_token")
        if token not in (FACEBOOK_TOKEN, FACEBOOK_USER_TOKEN):
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        if path == "me":
            return 200, {"id": FACEBOOK_PAGE, "name": "Trang Dưỡng Sinh"} if token == FACEBOOK_TOKEN else {
                "id": "999",
                "name": "Người dùng hệ thống",
            }
        if token == FACEBOOK_TOKEN:
            return 400, {"error": {"message": "(#100) Tried accessing nonexisting field (accounts)", "code": 100}}
        return 200, {"data": [page | {"access_token": FACEBOOK_TOKEN} for page in self.facebook_pages]}

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
        publishing = {
            "status": "not_started" if mode == "rejected" else "completed",
            "publish_status": "draft" if mode == "busy" else reel["state"],
        }
        if reel.get("scheduled_publish_time"):
            publishing["publish_time"] = int(reel["scheduled_publish_time"])
        return 200, {
            "id": video_id,
            "status": {
                "video_status": {"error": "error", "rejected": "processing", "busy": "processing"}.get(mode, "ready"),
                "uploading_phase": {"status": "complete" if reel["uploaded"] else "in_progress"},
                "processing_phase": {
                    "error": {"status": "error"},
                    "rejected": {"status": "not_started", "error": {"message": "Resolution too low"}},
                    "busy": {"status": "in_progress"},
                }.get(mode, {"status": "completed"}),
                "publishing_phase": publishing,
            },
        }

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
                data = (
                    body
                    if isinstance(body, bytes)
                    else (body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode())
                )
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
                if path == "/openverse/v1/auth_tokens/token/":
                    form = dict(urllib.parse.parse_qsl(raw.decode()))
                    self._send(*fake._openverse_token(form))
                    return
                body = json.loads(raw or b"{}")
                if path == "/v1/messages":
                    self._send(*fake._claude(body))
                elif path == "/openai/v1/chat/completions":
                    self._send(*fake._chat(self.headers.get("Authorization"), body))
                elif path.startswith("/gemini/v1beta/models/"):
                    self._send(*fake._image_gen(self.headers.get("x-goog-api-key"), body))
                elif path.startswith("/v1/text-to-speech/"):
                    status, reply = fake._tts(
                        path.removeprefix("/v1/text-to-speech/"), self.headers.get("xi-api-key"), body
                    )
                    self._send(status, reply, "audio/mpeg" if isinstance(reply, bytes) else "application/json")
                else:
                    self._send(404, {"error": "not found"})

            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                if parts.path == "/health":
                    self._send(200, {"ok": True})
                elif parts.path == "/v1/models":
                    # The Anthropic SDK sends the key as a bearer token; older clients use x-api-key.
                    bearer = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
                    self._send(*fake._models(None, self.headers.get("x-api-key") or bearer))
                elif parts.path == "/openai/v1/models":
                    self._send(*fake._models(self.headers.get("Authorization"), None))
                elif parts.path.startswith("/facebook/"):
                    query = dict(urllib.parse.parse_qsl(parts.query))
                    target = parts.path.removeprefix("/facebook/")
                    if target in ("me", "me/accounts"):
                        self._send(*fake._me(target, query))
                    else:
                        self._send(*fake._reel_status(target, query))
                elif parts.path == "/api/":
                    self._send(*fake._pixabay(dict(urllib.parse.parse_qsl(parts.query))))
                elif parts.path == "/pexels/v1/search":
                    query = dict(urllib.parse.parse_qsl(parts.query))
                    self._send(*fake._pexels(query, self.headers.get("Authorization")))
                elif parts.path == "/openverse/v1/images/":
                    authorized = self.headers.get("Authorization") == f"Bearer {OPENVERSE_TOKEN}"
                    self._send(*fake._openverse(dict(urllib.parse.parse_qsl(parts.query)), authorized))
                elif parts.path.startswith("/img/"):
                    self._send(200, fake._image(parts.path.removeprefix("/img/").removesuffix(".jpg")), "image/jpeg")
                else:
                    self._send(404, {"error": "not found"})

        return Handler


if __name__ == "__main__":
    services = FakeServices(int(sys.argv[1]))
    # E2E videos stay short so the render finishes quickly.
    services.default_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    print(f"Fake Claude/Pixabay/ElevenLabs/Gemini/Facebook on {services.url}", flush=True)
    services.server.serve_forever()
