"""Local stand-ins for the Claude Messages API, an OpenAI-compatible chat API, the stock sources (Pixabay, Pexels, Openverse),
ElevenLabs TTS, Gemini and Cloudflare Workers AI image generation and Facebook Reels, for pytest and E2E.

The app reaches them only through ANTHROPIC_BASE_URL, PIXABAY_API_URL, PEXELS_API_URL,
OPENVERSE_API_URL, ELEVENLABS_API_URL, IMAGE_GEN_API_URL, IMAGE_GEN_CF_API_URL and FACEBOOK_API_URL,
so production code has no test switches. The OpenAI-compatible API (at <url>/openai/v1) is reached the way a
member sets any provider up, through its base URL on /settings/ai. Run `python fake_services.py <port>` for E2E; pytest starts FakeServices in a thread.
"""

import base64
import hashlib
import io
import json
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from email import policy as email_policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

PIXABAY_KEY = "fake-pixabay-key"
PEXELS_KEY = "fake-pexels-key"
OPENVERSE_CLIENT_ID = "fake-openverse-client"
OPENVERSE_CLIENT_SECRET = "fake-openverse-secret"
OPENVERSE_TOKEN = "fake-openverse-token"
ELEVENLABS_KEY = "fake-elevenlabs-key"
IMAGE_GEN_KEY = "fake-image-gen-key"
IMAGE_GEN_CF_KEY = "fake-cloudflare-token"
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
        "title_image_prompt": "Calcium-rich Vietnamese dishes on one wooden table, top-down view",
        "title_voice": "Mời bạn xem đến cuối nhé",
        "scenes": [
            {
                "text": f"{food}\nGiàu *canxi*",
                "seconds": seconds,
                "voice": f"{food} giàu canxi",
                "keywords": [food.lower(), "món ăn"],
                "keywords_en": [english, "food"] if english else [],
                "image_prompt": f"A plate of {english or food} on a wooden table, close-up",
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


PAIN_GROUPS = ["Huyết áp và tim mạch", "Đường huyết", "Xương khớp", "Mất ngủ", "Tiêu hóa và gan", "Da và tóc"]


def plan_json(first: int, last: int, per_day: int = 4) -> dict:
    """A 30-day plan answer for days `first` to `last`, every topic different."""
    return {
        "days": [
            {
                "day": day,
                "ideas": [
                    {
                        "topic": f"{5 + 2 * (n % 2)} món tốt cho sức khỏe ngày {day} ý {n}",
                        "pain_group": PAIN_GROUPS[(day + n) % len(PAIN_GROUPS)],
                        "pain": f"Nỗi đau ngày {day} ý {n}",
                        "hook": f"Hook ngày {day} ý {n}",
                    }
                    for n in range(1, per_day + 1)
                ],
            }
            for day in range(first, last + 1)
        ]
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
        self.pixabay_mode = "ok"  # ok | empty | error500 | hang | rate_limit | cloudflare_block
        # name -> (imageWidth, imageHeight) of the original, sent with that result; others carry no size.
        self.pixabay_sizes: dict[str, tuple[int, int]] = {}
        # (source, query parameters) of every photo search, to check the filters each source was asked for.
        self.stock_searches: list[tuple[str, dict]] = []
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
        self.clip_queries: list[tuple[str, str]] = []  # (source, keyword) of video clip searches
        self.clip_downloads: list[str] = []
        self._clip_bytes: bytes | None = None
        self.default_seconds = 4.0
        self.tts_mode = "ok"  # ok | quota | error500
        self.tts_ok_count: int | None = None  # with a number, only that many requests succeed, then "quota"
        self.image_gen_mode = "ok"  # ok | quota | error500
        self.image_gen_ok_count: int | None = None  # with a number, only that many requests succeed, then "quota"
        self.image_gen_refused: list[str] = []  # a prompt containing one of these is safety-refused (200, no image)
        self.image_gen_prompts: list[str] = []
        # Cloudflare Workers AI, apart from Gemini's state.
        self.cf_image_gen_mode = "ok"  # ok | quota | error500
        self.cf_image_gen_ok_count: int | None = None  # with a number, only that many requests succeed, then "quota"
        self.cf_image_gen_refused: list[str] = []  # a prompt containing one of these is refused (200, success false)
        self.cf_image_gen_prompts: list[str] = []
        self.tts_requests: list[dict] = []  # {"voice_id", "text", "model_id", "language_code", "speed"}
        self.voice_list_requests = 0
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
        self.facebook_delete_refusals = 0  # that many deletes are refused: 403 and the reel stays
        self.facebook_cover_refusals = 0  # that many covers are refused: 400 and the reel keeps its own
        # A reel's numbers by video_id: views, shares, comments, reactions; a missing one is left out of the answer.
        self.facebook_insights: dict[str, dict[str, int]] = {}
        self.facebook_insights_calls = 0
        self.facebook_insights_refused = False  # the token lacks read_insights: 403, code 200
        self.facebook_insights_gone: set[str] = set()  # reels Facebook no longer has
        self.facebook_followers: int | None = 1200  # a Page's followers_count; None leaves it out of the answer
        self.facebook_page_info_refused = False  # the token cannot read the Page: 403, code 200
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
            # IMAGE_GEN_PROVIDER is left unset: both providers are set up, so Cloudflare is the default
            # (image_providers.default); the Gemini tests set it themselves.
            "IMAGE_GEN_CF_API_URL": f"{self.url}/cloudflare/client/v4",
            "IMAGE_GEN_CF_ACCOUNT_ID": "test-account",
            "IMAGE_GEN_CF_API_KEY": IMAGE_GEN_CF_KEY,
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
        plan = re.search(r"chỉ lập ngày (\d+) đến ngày (\d+), mỗi ngày đúng (\d+) ý tưởng", prompt)
        if reply is None and plan:
            reply = plan_json(*(int(number) for number in plan.groups()))
        elif reply is None:
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

    def _voices(self, key: str | None) -> tuple[int, dict]:
        with self.lock:
            self.voice_list_requests += 1
        if key != ELEVENLABS_KEY:
            return 401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}
        return 200, {
            "voices": [
                {
                    "voice_id": "pNInz6obpgDQGcFmaJgB",
                    "name": "Adam",
                    "labels": {"gender": "male", "age": "middle aged", "accent": "american"},
                    "preview_url": f"{self.url}/voice-samples/adam.mp3",
                },
                {
                    "voice_id": "fake-voice-mai",
                    "name": "Mai",
                    "labels": {"gender": "female", "accent": "vietnamese"},
                    "preview_url": None,
                },
            ]
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

    def _clip_hits(self, source: str, keyword: str) -> list[str]:
        with self.lock:
            self.clip_queries.append((source, keyword))
        return [hashlib.sha1(f"{source}-{keyword}-{n}".encode()).hexdigest()[:8] for n in range(1, 4)]

    def _pexels_videos(self, query: dict, key: str | None) -> tuple[int, object]:
        if key != PEXELS_KEY:
            return 401, {"error": "Unauthorized"}
        videos = [
            {
                "id": int(name, 16),
                "image": self.image_url(f"clip-{name}"),
                "duration": 3,
                "video_files": [
                    {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": f"{self.url}/clips/{name}.mp4"},
                    {"file_type": "video/mp4", "width": 360, "height": 640, "link": f"{self.url}/clips/{name}-sd.mp4"},
                ],
            }
            for name in self._clip_hits("pexels", query.get("query", ""))
        ]
        return 200, {"videos": videos, "total_results": len(videos)}

    def _pixabay_videos(self, query: dict) -> tuple[int, object]:
        if query.get("key") != PIXABAY_KEY:
            return 400, "[ERROR 400] Invalid or missing API key"
        hits = [
            {
                "id": int(name, 16),
                "duration": 3,
                "videos": {
                    "medium": {
                        "url": f"{self.url}/clips/{name}.mp4",
                        "width": 1280,
                        "height": 720,
                        "thumbnail": self.image_url(f"clip-{name}"),
                    },
                    "small": {"url": f"{self.url}/clips/{name}-sd.mp4", "width": 640, "height": 360, "thumbnail": ""},
                },
            }
            for name in self._clip_hits("pixabay", query.get("q", ""))
        ]
        return 200, {"total": len(hits), "totalHits": len(hits), "hits": hits}

    def _clip(self, name: str) -> bytes:
        """A 3 s vertical test clip, made once with FFmpeg."""
        with self.lock:
            self.clip_downloads.append(name)
            if self._clip_bytes is None:
                self._clip_bytes = subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-f",
                        "lavfi",
                        "-i",
                        "testsrc=size=720x1280:rate=30:duration=3",
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart+frag_keyframe+empty_moov",
                        "-f",
                        "mp4",
                        "-",
                    ],
                    capture_output=True,
                    check=True,
                ).stdout
            return self._clip_bytes

    def _pixabay(self, query: dict) -> tuple[int, object]:
        keyword = query.get("q", "")
        with self.lock:
            self.pixabay_queries.append(keyword)
            self.stock_searches.append(("pixabay", {k: v for k, v in query.items() if k != "key"}))
        if self.pixabay_mode == "cloudflare_block":
            # Cloudflare's bot check in front of Pixabay: an HTML page, whatever the key.
            return 429, b"<!DOCTYPE html><html><head><title>Just a moment...</title></head><body></body></html>"
        if self.pixabay_mode == "rate_limit":
            return 429, "API rate limit exceeded"
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
            | (
                {"imageWidth": self.pixabay_sizes[name][0], "imageHeight": self.pixabay_sizes[name][1]}
                if name in self.pixabay_sizes
                else {}
            )
            for n, name in enumerate(names)
        ]
        return 200, {"total": len(hits), "totalHits": len(hits), "hits": hits}

    def _pexels(self, query: dict, key: str | None) -> tuple[int, object]:
        keyword = query.get("query", "")
        with self.lock:
            self.pexels_queries.append(keyword)
            self.stock_searches.append(("pexels", dict(query)))
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
            self.stock_searches.append(("openverse", dict(query)))
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
                # Only a request that set a speed records one.
                | ({"speed": body["voice_settings"]["speed"]} if body.get("voice_settings") else {})
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

    def _cf_image_gen(self, authorization: str | None, body: dict) -> tuple[int, dict]:
        prompt = str(body.get("prompt") or "")
        with self.lock:
            self.cf_image_gen_prompts.append(prompt)
            calls = len(self.cf_image_gen_prompts)

        def failed(status: int, code: int, message: str) -> tuple[int, dict]:
            return status, {
                "result": None,
                "success": False,
                "errors": [{"code": code, "message": message}],
                "messages": [],
            }

        if authorization != f"Bearer {IMAGE_GEN_CF_KEY}":
            return failed(401, 10000, "Authentication error")
        if self.cf_image_gen_mode == "error500":
            return failed(500, 7000, "Internal server error")
        if self.cf_image_gen_mode == "quota" or (
            self.cf_image_gen_ok_count is not None and calls > self.cf_image_gen_ok_count
        ):
            return failed(429, 4006, "you have used up your daily free allocation of 10,000 neurons")
        if any(marker in prompt for marker in self.cf_image_gen_refused):
            return failed(200, 3030, "content policy violation: the prompt was flagged")
        # FLUX.1 schnell on Cloudflare ignores width/height and always answers a 1024x1024 JPEG.
        digest = hashlib.sha1(prompt.encode()).digest()
        buffer = io.BytesIO()
        Image.new("RGB", (1024, 1024), (digest[0], digest[1], digest[2])).save(buffer, "JPEG", quality=90)
        image = base64.b64encode(buffer.getvalue()).decode()
        return 200, {"result": {"image": image}, "success": True, "errors": [], "messages": []}

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

    def _reel_cover(self, video_id: str, content_type: str, raw: bytes) -> tuple[int, dict]:
        """Video Thumbnails: a multipart form with the image as `source`."""
        message = BytesParser(policy=email_policy.default).parsebytes(
            f"Content-Type: {content_type}\r\n\r\n".encode() + raw
        )
        fields = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
        token = fields["access_token"].get_content() if "access_token" in fields else None
        if token != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        with self.lock:
            reel = self.reels.get(video_id)
            if reel is None:
                return 404, {"error": {"message": "Unknown video", "code": 100}}
            if self.facebook_cover_refusals:
                self.facebook_cover_refusals -= 1
                return 400, {"error": {"message": "Invalid parameter", "code": 100}}
            reel["cover"] = fields["source"].get_payload(decode=True)
            reel["cover_preferred"] = fields["is_preferred"].get_content()
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

    def _page_info(self, page_id: str, query: dict) -> tuple[int, dict]:
        """GET /{page-id}?fields=name,followers_count with the Page's own token."""
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        if self.facebook_page_info_refused:
            return 403, {"error": {"message": "(#200) Requires pages_read_engagement permission", "code": 200}}
        page = next(page for page in self.facebook_pages if page["id"] == page_id)
        reply = {"id": page_id, "name": page["name"]}
        if self.facebook_followers is not None:
            reply["followers_count"] = self.facebook_followers
        return 200, reply

    def _reel_insights(self, video_id: str, query: dict) -> tuple[int, dict]:
        """Video Insights in the shape Meta documents: one entry per metric, its lifetime value in `values`."""
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        with self.lock:
            self.facebook_insights_calls += 1
            if self.facebook_insights_refused:
                return 403, {"error": {"message": "(#200) Requires read_insights permission", "code": 200}}
            if video_id in self.facebook_insights_gone or self.reels.get(video_id, {}).get("lost"):
                return 400, {"error": {"message": "Unsupported get request", "code": 100, "error_subcode": 33}}
            numbers = self.facebook_insights.get(video_id, {"views": 1200, "shares": 3, "comments": 5, "reactions": 40})

        def metric(name: str, value: object) -> dict:
            return {
                "name": name,
                "period": "lifetime",
                "values": [{"value": value}],
                "id": f"{video_id}/insights/{name}",
            }

        data = []
        if "views" in numbers:
            data.append(metric("fb_reels_total_plays", numbers["views"]))
        social = {key.upper(): numbers[key + "s"] for key in ("share", "comment") if key + "s" in numbers}
        if social:
            data.append(metric("post_video_social_actions", social))
        if "reactions" in numbers:
            data.append(metric("post_video_likes_by_reaction_type", {"REACTION_LIKE": numbers["reactions"]}))
        return 200, {"data": data}

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

    def _delete_reel(self, video_id: str, query: dict) -> tuple[int, dict]:
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        with self.lock:
            if self.facebook_delete_refusals:
                self.facebook_delete_refusals -= 1
                return 403, {"error": {"message": "Permissions error", "code": 200}}
            if self.reels.pop(video_id, None) is None:
                return 404, {"error": {"message": "Unknown video", "code": 100}}
        return 200, {"success": True}

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
                if path.startswith("/facebook/") and path.endswith("/thumbnails"):
                    video_id = path.removeprefix("/facebook/").removesuffix("/thumbnails")
                    self._send(*fake._reel_cover(video_id, self.headers.get("Content-Type", ""), raw))
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
                elif path.startswith("/cloudflare/client/v4/accounts/") and "/ai/run/" in path:
                    self._send(*fake._cf_image_gen(self.headers.get("Authorization"), body))
                elif path.startswith("/v1/text-to-speech/"):
                    status, reply = fake._tts(
                        path.removeprefix("/v1/text-to-speech/"), self.headers.get("xi-api-key"), body
                    )
                    self._send(status, reply, "audio/mpeg" if isinstance(reply, bytes) else "application/json")
                else:
                    self._send(404, {"error": "not found"})

            def do_DELETE(self):
                parts = urllib.parse.urlsplit(self.path)
                if parts.path.startswith("/facebook/"):
                    query = dict(urllib.parse.parse_qsl(parts.query))
                    self._send(*fake._delete_reel(parts.path.removeprefix("/facebook/"), query))
                else:
                    self._send(404, {"error": "not found"})

            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                if parts.path == "/health":
                    self._send(200, {"ok": True})
                elif parts.path == "/v1/voices":
                    self._send(*fake._voices(self.headers.get("xi-api-key")))
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
                    elif target in {page["id"] for page in fake.facebook_pages}:
                        self._send(*fake._page_info(target, query))
                    elif target.endswith("/video_insights"):
                        self._send(*fake._reel_insights(target.removesuffix("/video_insights"), query))
                    else:
                        self._send(*fake._reel_status(target, query))
                elif parts.path == "/api/videos/":
                    self._send(*fake._pixabay_videos(dict(urllib.parse.parse_qsl(parts.query))))
                elif parts.path == "/pexels/videos/search":
                    query = dict(urllib.parse.parse_qsl(parts.query))
                    self._send(*fake._pexels_videos(query, self.headers.get("Authorization")))
                elif parts.path.startswith("/clips/"):
                    self._send(200, fake._clip(parts.path.removeprefix("/clips/")), "video/mp4")
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
