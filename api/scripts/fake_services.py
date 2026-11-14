"""Local stand-ins for the Claude Messages API, an OpenAI-compatible chat API, the stock sources (Pixabay, Pexels, Openverse),
ElevenLabs and VieNeu TTS, Gemini and Cloudflare Workers AI image generation, Facebook Reels, Shopee Affiliate and TikTok
(Login Kit, Content Posting API), for pytest and E2E.

The app reaches them only through ANTHROPIC_BASE_URL, PIXABAY_API_URL, PEXELS_API_URL,
OPENVERSE_API_URL, ELEVENLABS_API_URL, VIENEU_API_URL, IMAGE_GEN_API_URL, IMAGE_GEN_CF_API_URL, FACEBOOK_API_URL,
SHOPEE_AFFILIATE_API_URL, SHOPEE_SHORT_LINK_URL and TIKTOK_API_URL,
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
UNSPLASH_KEY = "fake-unsplash-key"
ELEVENLABS_KEY = "fake-elevenlabs-key"
# Not in env(): VieNeu voices are offered only once a key is set, so tests set this one themselves.
VIENEU_KEY = "vn_test_fake-vieneu-key"
IMAGE_GEN_KEY = "fake-image-gen-key"
IMAGE_GEN_CF_KEY = "fake-cloudflare-token"
# What the fake inpainting model paints, so a test sees exactly which pixels it changed.
CF_INPAINT_COLOR = (255, 0, 255)
OPENAI_KEY = "fake-openai-key"
OPENAI_MODELS = ["fake-gpt-mini", "models/fake-gemini-flash"]
FACEBOOK_PAGE = "1234567"
FACEBOOK_TOKEN = "fake-facebook-token"  # the Page's own token, the only one that can post
# What Facebook answers for a reel it no longer has: not a 404, but the same 400 as for one the token may not read.
GONE = (
    400,
    {
        "error": {
            "message": "Unsupported get request. Object with ID does not exist, cannot be loaded due to missing "
            "permissions, or does not support this operation",
            "code": 100,
            "error_subcode": 33,
        }
    },
)
FACEBOOK_USER_TOKEN = "fake-facebook-user-token"  # manages the Page, gets the Page's token from /me/accounts
SHOPEE_APP_ID = "1000001"
SHOPEE_SECRET = "fake-shopee-secret"
TIKTOK_CLIENT_KEY = "fake-tiktok-client-key"
TIKTOK_CLIENT_SECRET = "fake-tiktok-client-secret"
TIKTOK_CODE = "fake-tiktok-code"  # the code TikTok's authorize page sends back for TIKTOK_OPEN_ID
TIKTOK_OPEN_ID = "tt-open-an"
# What /v2/user/info/ reads with user.info.basic; username, bio and stats need other scopes.
TIKTOK_BASIC_FIELDS = {"open_id", "union_id", "avatar_url", "avatar_url_100", "avatar_large_url", "display_name"}


def shopee_offer(item_id: int, name: str, **fields) -> dict:
    """A productOfferV2 node as Shopee sends it: numbers as strings, the rate as a fraction, times in seconds."""
    return {
        "itemId": item_id,
        "productName": name,
        "shopName": "Shop Sức Khỏe",
        "shopType": [1],
        "ratingStar": "4.9",
        "sales": 1500,
        "priceMin": "250000",
        "commissionRate": "0.08",
        "productLink": f"https://shopee.vn/product/1/{item_id}",
        "imageUrl": f"https://cf.shopee.vn/file/{item_id}",
        "periodEndTime": 0,
        **fields,
    }


def default_offers(keyword: str) -> list[dict]:
    """Three products per keyword: two meet the app's rules, the third has too few stars."""
    base = int(hashlib.sha1(keyword.encode()).hexdigest()[:6], 16) * 10
    return [
        shopee_offer(base + 1, f"{keyword} loại 1"),
        shopee_offer(base + 2, f"{keyword} loại 2", shopType=[2], priceMin="120000", commissionRate="0.05"),
        shopee_offer(base + 3, f"{keyword} loại 3", ratingStar="4.2"),
    ]


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


def analysis_json(frame_count: int) -> dict:
    return {
        "phan_tich": "Hook: câu hỏi gây tò mò ở giây đầu.\nCấu trúc: 3 món, mỗi món 3 giây.\nKêu gọi: lưu video.",
        "khung_hinh": [f"Khung {n}: bát cháo trên bàn gỗ" for n in range(1, frame_count + 1)],
    }


def learned_json(topic: str, seconds: float = 4, with_analysis: bool = False) -> dict:
    """A script learned from a sample video: the title and the first two scenes show stretches of the sample."""
    script = script_json(topic, seconds)
    script["title_clip"] = {"tu": 0, "den": 3}
    for index, scene in enumerate(script["scenes"]):
        scene["clip"] = {"tu": 1 + index, "den": 4 + index} if index < 2 else None
    if with_analysis:
        script["phan_tich"] = "Hook: câu hỏi ở giây đầu.\nNhịp: đổi cảnh mỗi 3 giây."
    return script


PAIN_GROUPS = ["Huyết áp và tim mạch", "Đường huyết", "Xương khớp", "Mất ngủ", "Tiêu hóa và gan", "Da và tóc"]


def revise_json(prompt: str) -> dict:
    """ "Nhờ AI sửa": the first note's scene gets a new on-screen text and a layer at its second; every note an answer."""
    notes = re.findall(r"^- Góp ý (\d+) \[[^\]]+\] (Cảnh tiêu đề|Cảnh (\d+)):", prompt, flags=re.MULTILINE)
    scene = int(notes[0][2]) if notes and notes[0][2] else 1
    return {
        "changes": [{"scene": scene, "text": "Đã sửa\n*theo góp ý*"}],
        "layers": [{"scene": scene, "start": 0.2, "seconds": 2, "text": "GIẢM *50%*"}],
        "replies": [{"note": int(number), "reply": f"Đã sửa theo góp ý {number}."} for number, _, _ in notes],
    }


def article_json(topic: str) -> dict:
    """An article caption ("Bài viết", articles.output_format) about `topic`."""
    return {
        "hook": f"Bạn có đang hiểu sai về {topic}?",
        "body": "Nhiều người làm theo thói quen.\nThật ra chỉ cần đổi một chút.\nCơ thể sẽ nhẹ nhàng hơn.",
        "note": "Ai đang có bệnh nền thì hỏi bác sĩ trước khi đổi thói quen nhé.",
        "question": "Bạn đã thử cách này chưa?",
        "hashtags": ["#suckhoe", "#meovat"],
        "pinned_comment": "Bạn làm cách này lâu chưa, kể mình nghe với!",
        "affiliates": ["bình giữ nhiệt"],
    }


def text_looks_json() -> dict:
    """ "AI gợi ý" of a group's "Chữ & phụ đề": three looks, one of them with a value the app refuses."""
    return {
        "options": [
            {
                "name": "Ấm áp dễ đọc",
                "reason": "Hộp trắng chữ to, hợp người lớn tuổi.",
                "look": {"text_style": "white", "text_size": "large", "text_case": "keep", "captions": "phrase"},
            },
            {
                "name": "Nổi bật",
                "reason": "Hộp đỏ, tô vàng từng từ.",
                "look": {"text_style": "red", "accent_color": "#FFD400", "captions": "word"},
            },
            {"name": "Tối giản", "reason": "Chữ viền không hộp.", "look": {"text_style": "none", "text_size": "huge"}},
        ]
    }


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


# A reel's numbers when a test sets none: what a fresh, ordinary reel gives.
DEFAULT_ARTICLE_NUMBERS = {"reach": 400, "shares": 2, "comments": 6, "reactions": 30}
DEFAULT_REEL_NUMBERS = {
    "views": 1200,
    "shares": 3,
    "comments": 5,
    "reactions": 40,
    "plays": 1000,
    "replays": 200,
    "reach": 900,
    "avg_watch_ms": 8400,
    "view_time_ms": 10080000,
    "followers": 4,
    "retention": {
        str(index): share for index, share in enumerate((1, 0.82, 0.7, 0.6, 0.52, 0.45, 0.4, 0.36, 0.33, 0.3))
    },
}


class FakeServices:
    def __init__(self, port: int = 0):
        self.lock = threading.Lock()
        self.claude_replies: list[object] = []  # str (raw text) or dict (JSON); empty: a valid script
        self.claude_hang = False
        self.claude_prompts: list[str] = []
        # How many images each LLM request carried, in step with claude_prompts ("Từ video mẫu" sends stills).
        self.claude_image_counts: list[int] = []
        # ElevenLabs Speech-to-Text: what it says it heard, and the files it was sent.
        # ok | quota | no_permission (a key made without the speech_to_text permission, as ElevenLabs answers it)
        self.stt_mode = "ok"
        self.stt_words: list[dict] = [
            {"text": "Ba", "start": 0.2, "end": 0.4, "type": "word"},
            {"text": "món", "start": 0.4, "end": 0.6, "type": "word"},
            {"text": "ăn", "start": 0.6, "end": 0.8, "type": "word"},
            {"text": "sáng", "start": 0.8, "end": 1.0, "type": "word"},
            {"text": "tốt", "start": 1.0, "end": 1.2, "type": "word"},
            {"text": "cho", "start": 1.2, "end": 1.4, "type": "word"},
            {"text": "tim.", "start": 1.4, "end": 1.6, "type": "word"},
            {"text": "Món", "start": 3.1, "end": 3.3, "type": "word"},
            {"text": "đầu", "start": 3.3, "end": 3.5, "type": "word"},
            {"text": "tiên.", "start": 3.5, "end": 3.8, "type": "word"},
        ]
        self.stt_requests: list[dict] = []  # {"model_id", "bytes"}
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
        self.wikimedia_mode = "ok"  # ok | error500 | rate_limit
        # keyword -> [{"name", "license", "artist", "attribution", "width", "height", "mime"}]; missing keys default.
        self.wikimedia_results: dict[str, list[dict]] = {}
        self.wikimedia_queries: list[str] = []  # the gsrsearch text as sent
        self.wikimedia_agents: list[str] = []  # the User-Agent of every Wikimedia search
        self.unsplash_mode = "ok"  # ok | error500 | rate_limit
        self.unsplash_results: dict[str, list[str]] = {}
        self.unsplash_queries: list[str] = []
        self.unsplash_downloads: list[str] = []  # names whose download_location was called, with the key
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
        # Cloudflare's inpainting model ("Sửa ảnh" › "Xóa vùng"): each request's prompt and the sizes of the image and
        # mask it sent; it answers the PNG itself, all of it CF_INPAINT_COLOR.
        self.cf_inpaint_mode = "ok"  # ok | quota | error500
        self.cf_inpaint_requests: list[dict] = []
        # Gemini asked to edit a photo ("Sửa theo mô tả"): each request's words and the size of the photo it sent.
        self.image_edit_requests: list[dict] = []
        self.tts_requests: list[dict] = []  # {"voice_id", "text", "model_id", "language_code", "speed"}
        self.voice_list_requests = 0
        # VieNeu (OpenAI-compatible /v1/audio/speech): {"voice", "input", "model", "response_format", "authorization"}
        self.vieneu_requests: list[dict] = []
        self.vieneu_mode = "ok"  # ok | trial_limit | error500
        self.reels: dict[str, dict] = {}  # video_id -> {"uploaded", "bytes", "finishes", "state", "description", ...}
        # Photo and text posts on the Page's feed ("Bài viết"), by post id: {"message", "published", "scheduled",
        # "photo": bytes or None}; their numbers by post id (reach, shares, comments, reactions).
        self.page_posts: dict[str, dict] = {}
        self.page_post_calls = 0
        self.page_post_replies_lost = 0  # that many posts are made, then answer 500
        self.page_post_refusals = 0  # that many posts are refused: 400 and nothing is posted
        self.page_post_numbers: dict[str, dict] = {}
        self.page_post_reach_retired = False  # post_total_media_view_unique is refused, (#100) like a retired metric
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
        self.facebook_insights: dict[str, dict] = {}
        self.facebook_insights_calls = 0
        self.facebook_insights_refused = False  # the token lacks read_insights: 403, code 200
        self.facebook_insights_gone: set[str] = set()  # reels Facebook no longer has
        # Video Insights metrics Meta has retired: a call asking for any of them fails whole, (#100) like Meta's.
        self.facebook_retired_metrics: set[str] = set()
        self.facebook_followers: int | None = 1200  # a Page's followers_count; None leaves it out of the answer
        # A Page's profile picture link (picture{url}); None leaves it out of the answer.
        self.facebook_picture: str | None = None
        self.facebook_page_info_refused = False  # the token cannot read the Page: 403, code 200
        # Comments by id: {"object": reel id, "message", "from": {"id", "name"}, "edits"}
        self.facebook_comments: dict[str, dict] = {}
        self.facebook_comment_refused = False  # the token lacks pages_manage_engagement: 403, code 200
        self.facebook_comment_replies_lost = 0  # that many comments are written, then answer 500
        # Reels whose comments the token cannot read: 400, code 100, subcode 33, as Facebook answers for a reel it
        # will not show this token and for one it no longer has (a lost reel's comments answer the same).
        self.facebook_comments_unreadable: set[str] = set()
        # Page Insights by metric name: {end_time: value}; a metric in `facebook_page_metrics_dropped` is refused as
        # Meta refuses a retired one, and `facebook_page_insights_refused` refuses them all (no read_insights).
        self.facebook_page_insights: dict[str, dict[str, int]] = {
            "page_media_view": {"2026-11-02T08:00:00+0000": 900, "2026-11-03T08:00:00+0000": 1100},
            "page_total_media_view_unique": {"2026-11-02T08:00:00+0000": 600, "2026-11-03T08:00:00+0000": 700},
            "page_post_engagements": {"2026-11-02T08:00:00+0000": 40, "2026-11-03T08:00:00+0000": 55},
        }
        self.facebook_page_metrics_dropped: set[str] = set()
        # Shopee Affiliate: the apps it knows (App ID -> Secret, checked in the signature), its answers and its calls.
        self.shopee_apps = {SHOPEE_APP_ID: SHOPEE_SECRET}
        self.shopee_mode = "ok"  # ok | rate_limit | error500
        self.shopee_offers: dict[str, list[dict]] = {}  # keyword -> nodes; a missing keyword gets default_offers
        self.shopee_items: dict[int, dict | None] = {}  # itemId -> node now; None: no longer offered
        self.shopee_conversions: list[dict] = []  # conversionReport nodes
        self.shopee_queries: list[str] = []
        self.shopee_links: list[dict] = []  # {"origin", "sub_ids", "link"}
        # s.shopee.vn/<code> -> where it redirects, as Shopee's affiliate redirect writes it; a missing code is a 404.
        self.shopee_short_links: dict[str, str] = {}
        self.facebook_page_insights_refused = False
        # TikTok (Login Kit + Content Posting API): the accounts it knows by open_id, which code logs in which one,
        # the tokens it gave (each refresh replaces the refresh token: the old one stops working), and its posts by
        # publish_id: {"mode", "post_info", "source_info", "bytes", "reads"}.
        self.tiktok_users: dict[str, dict] = {
            TIKTOK_OPEN_ID: {
                "open_id": TIKTOK_OPEN_ID,
                "union_id": "tt-union-an",
                "username": "anlanhsk",
                "display_name": "An Lành SK",
                "avatar_url": "https://p16.tiktokcdn.com/an.jpg",
            }
        }
        self.tiktok_codes: dict[str, str] = {TIKTOK_CODE: TIKTOK_OPEN_ID}
        self.tiktok_access: dict[str, str] = {}  # access token -> open_id
        self.tiktok_refresh: dict[str, str] = {}  # refresh token -> open_id
        self.tiktok_token_count = 0
        self.tiktok_expires_in = 86400
        self.tiktok_revoked: list[str] = []
        self.tiktok_privacy_options = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]
        self.tiktok_unaudited = False  # a direct post other than SELF_ONLY is refused, as before TikTok's audit
        self.tiktok_init_error: str | None = None  # an error code every init answers with (e.g. rate_limit_exceeded)
        self.tiktok_upload_fails = 0  # that many chunk uploads answer 500
        self.tiktok_busy_reads = 0  # that many status reads say PROCESSING_DOWNLOAD before the final status
        self.tiktok_post_fails = False  # the final status is FAILED
        self.tiktok_posts: dict[str, dict] = {}
        self.tiktok_calls: list[str] = []  # the path of every TikTok call, in order
        # oEmbed answers by the post's link ("Dán link bài đã đăng"): one set here, else a plain answer naming the
        # TikTok account in the link (YouTube: @anngon); a link in `oembed_gone` answers 404, as a removed post.
        self.oembed: dict[str, dict] = {}
        self.oembed_gone: set[str] = set()
        self.oembed_calls: list[str] = []
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
            "WIKIMEDIA_API_URL": f"{self.url}/wikimedia/w/api.php",
            "UNSPLASH_API_URL": f"{self.url}/unsplash",
            "UNSPLASH_ACCESS_KEY": UNSPLASH_KEY,
            "OPENVERSE_CLIENT_ID": OPENVERSE_CLIENT_ID,
            "OPENVERSE_CLIENT_SECRET": OPENVERSE_CLIENT_SECRET,
            "ELEVENLABS_API_KEY": ELEVENLABS_KEY,
            "ELEVENLABS_API_URL": self.url,
            "VIENEU_API_URL": f"{self.url}/vieneu/api",
            "VIENEU_API_KEY": "",  # a key from a developer's .env must not offer VieNeu voices in every test
            "IMAGE_GEN_API_KEY": IMAGE_GEN_KEY,
            "IMAGE_GEN_API_URL": f"{self.url}/gemini",
            # IMAGE_GEN_PROVIDER is left unset: both providers are set up, so Cloudflare is the default
            # (image_providers.default); the Gemini tests set it themselves.
            "IMAGE_GEN_CF_API_URL": f"{self.url}/cloudflare/client/v4",
            "IMAGE_GEN_CF_ACCOUNT_ID": "test-account",
            "IMAGE_GEN_CF_API_KEY": IMAGE_GEN_CF_KEY,
            "FACEBOOK_API_URL": f"{self.url}/facebook",
            "SHOPEE_AFFILIATE_API_URL": f"{self.url}/shopee/graphql",
            "SHOPEE_SHORT_LINK_URL": f"{self.url}/shopee-short",
            "TIKTOK_API_URL": f"{self.url}/tiktok",
            "TIKTOK_OEMBED_URL": f"{self.url}/oembed/tiktok",
            "YOUTUBE_OEMBED_URL": f"{self.url}/oembed/youtube",
            "TIKTOK_CLIENT_KEY": TIKTOK_CLIENT_KEY,
            "TIKTOK_CLIENT_SECRET": TIKTOK_CLIENT_SECRET,
        }

    def image_url(self, name: str) -> str:
        return f"{self.url}/img/{name}.jpg"

    # --- request handling ---

    def _claude(self, body: dict) -> tuple[int, dict]:
        content = body["messages"][-1]["content"]
        images = 0
        if isinstance(content, list):
            # Images (Anthropic "image" blocks, OpenAI "image_url" parts) then the text.
            images = sum(1 for part in content if part.get("type") in ("image", "image_url"))
            content = "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
        prompt = content
        with self.lock:
            self.claude_prompts.append(prompt)
            self.claude_image_counts.append(images)
            reply = self.claude_replies.pop(0) if self.claude_replies else None
        while self.claude_hang:
            time.sleep(0.2)
        plan = re.search(r"chỉ lập ngày (\d+) đến ngày (\d+), mỗi ngày đúng (\d+) ý tưởng", prompt)
        frames = re.search(r'"khung_hinh": đúng (\d+) chuỗi', prompt)
        article = re.search(r"về chủ đề: (.+)", prompt) if '"hook": "1 dòng mở đầu"' in prompt else None
        if reply is None and article:
            reply = article_json(article.group(1).strip().rstrip("."))
        elif reply is None and plan:
            reply = plan_json(*(int(number) for number in plan.groups()))
        elif reply is None and frames:
            reply = analysis_json(int(frames.group(1)))
        elif reply is None and "THÊM VÀO OBJECT JSON TRÊN" in prompt:
            topic = prompt.split("theo đúng khung đó:\n", 1)[-1].split("\n", 1)[0].strip() or "sức khỏe"
            reply = learned_json(topic, self.default_seconds, with_analysis='"phan_tich"' in prompt)
        elif reply is None and "<gop-y>" in prompt:
            reply = revise_json(prompt)
        elif reply is None and "phong cách chữ và phụ đề KHÁC HẲN" in prompt:
            reply = text_looks_json()
        elif reply is None:
            topic = prompt.split("Chủ đề: ", 1)[-1].split("\n", 1)[0].strip() or "sức khỏe"
            reply = script_json(topic, self.default_seconds)
            if "HIỆU ỨNG CHO TỪNG CẢNH" in prompt:
                # "AI gợi ý hiệu ứng": a transition on every scene, a sound on the first, a line of text on the second.
                for index, scene in enumerate(reply["scenes"]):
                    scene["effects"] = {"transition": ["circle", "zoom", "slide"][index % 3], "color": None}
                reply["scenes"][0]["effects"]["sounds"] = [{"sound": "ding", "start": 0.2}]
                reply["scenes"][1]["effects"]["layer"] = {"text": "Dễ *trồng*", "start": 0, "seconds": 1}
            if "KIỂU CHỮ CHO VIDEO NÀY" in prompt:
                # "AI chọn kiểu chữ cho từng video": a dark box, kept as typed, captions word by word.
                reply["text_look"] = {"text_style": "dark", "text_case": "keep", "captions": "word"}
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

    def _wikimedia(self, query: dict, agent: str) -> tuple[int, object]:
        search = query.get("gsrsearch", "")
        with self.lock:
            self.wikimedia_queries.append(search)
            self.wikimedia_agents.append(agent)
            self.stock_searches.append(("wikimedia", dict(query)))
        if self.wikimedia_mode == "error500":
            return 500, {"error": "server error"}
        if self.wikimedia_mode == "rate_limit":
            return 429, {"error": {"code": "ratelimited"}}
        keyword = search.replace("filetype:bitmap", "").strip()
        entries = self.wikimedia_results.get(keyword)
        if entries is None:
            entries = [
                {"name": hashlib.sha1(f"wikimedia-{keyword}-{n}".encode()).hexdigest()[:10]} for n in range(1, 4)
            ]
        pages = []
        for index, entry in enumerate(entries, 1):
            name = entry["name"]
            license_name = entry.get("license", "Public domain")
            meta = {
                "LicenseShortName": {"value": license_name},
                "Artist": {
                    "value": entry.get(
                        "artist", f'<a href="https://commons.wikimedia.org/wiki/User:{name}">Tác giả {name}</a>'
                    )
                },
                "AttributionRequired": {"value": entry.get("attribution", "false")},
            }
            width, height = entry.get("width", 1280), entry.get("height", 1600)
            pages.append(
                {
                    "pageid": index,
                    "ns": 6,
                    "title": f"File:{name}.jpg",
                    "index": index,
                    "imageinfo": [
                        {
                            "url": self.image_url(name),
                            "descriptionurl": f"{self.url}/wikimedia/wiki/File:{name}.jpg",
                            "width": width,
                            "height": height,
                            "thumburl": self.image_url(name),
                            "thumbwidth": width,
                            "thumbheight": height,
                            "mime": entry.get("mime", "image/jpeg"),
                            "extmetadata": meta,
                        }
                    ],
                }
            )
        # Like the real API, pages come in no particular order: `index` gives the search's.
        return 200, {"batchcomplete": True, "query": {"pages": list(reversed(pages))}}

    def _unsplash(self, query: dict, authorization: str | None) -> tuple[int, object]:
        keyword = query.get("query", "")
        with self.lock:
            self.unsplash_queries.append(keyword)
            self.stock_searches.append(("unsplash", dict(query)))
        if authorization != f"Client-ID {UNSPLASH_KEY}":
            return 401, {"errors": ["OAuth error: The access token is invalid"]}
        if self.unsplash_mode == "rate_limit":
            return 403, "Rate Limit Exceeded"
        if self.unsplash_mode == "error500":
            return 500, {"errors": ["server error"]}
        names = self.unsplash_results.get(keyword) or [
            hashlib.sha1(f"unsplash-{keyword}-{n}".encode()).hexdigest()[:10] for n in range(1, 4)
        ]
        results = [
            {
                "id": name,
                "width": 3000,
                "height": 4500,
                "urls": {size: self.image_url(name) for size in ("raw", "full", "regular", "small", "thumb")},
                "links": {"download_location": f"{self.url}/unsplash/photos/{name}/download"},
                "user": {"name": f"Photographer {name}"},
            }
            for name in names
        ]
        return 200, {"total": len(results), "total_pages": 1, "results": results}

    def _unsplash_download(self, name: str, authorization: str | None) -> tuple[int, object]:
        if authorization != f"Client-ID {UNSPLASH_KEY}":
            return 401, {"errors": ["OAuth error: The access token is invalid"]}
        with self.lock:
            self.unsplash_downloads.append(name)
        return 200, {"url": self.image_url(name)}

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
        return 200, self._tone(str(body.get("text", "")))

    VIENEU_VOICES = [
        {"id": "Ngọc Lan", "name": "Ngọc Lan", "description": "Nữ · Bắc · Truyền cảm", "engine": "v4"},
        {"id": "Đăng Quân", "name": "Đăng Quân", "description": "Nam · Nam · Review", "engine": "v4"},
    ]

    def _vieneu_voices(self, query: dict) -> tuple[int, dict]:
        # Public on the real service: the key is not checked, the engine filter is.
        voices = [voice for voice in self.VIENEU_VOICES if voice["engine"] == query.get("engine", "v4")]
        return 200, {"voices": [voice | {"gender": "female", "region": "north", "kind": "catalog"} for voice in voices]}

    def _vieneu_speech(self, authorization: str | None, body: dict) -> tuple[int, object]:
        with self.lock:
            self.vieneu_requests.append(
                {name: body.get(name) for name in ("voice", "input", "model", "response_format")}
                | {"authorization": authorization}
            )

        def failed(status: int, message: str, code: str | None = None) -> tuple[int, dict]:
            return status, {"error": {"message": message, "type": "error", "param": None, "code": code}}

        if authorization != f"Bearer {VIENEU_KEY}":
            return failed(401, "Invalid or revoked API key.")
        if self.vieneu_mode == "trial_limit":
            return failed(429, "Trial daily limit reached.", "TRIAL_API_DAILY_LIMIT")
        if self.vieneu_mode == "error500":
            return failed(500, "server error")
        if body.get("voice") not in {voice["id"] for voice in self.VIENEU_VOICES}:
            return failed(400, "Unknown voice for engine v4.")
        return 200, self._tone(str(body.get("input", "")))

    @staticmethod
    def _tone(text: str) -> bytes:
        # A tone instead of speech, 0.3 s per word, so tests can tell how long each narration is.
        seconds = 0.3 * max(1, len(text.split()))
        return subprocess.run(
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

    def _image_gen(self, key: str | None, body: dict) -> tuple[int, dict]:
        try:
            parts = list(body["contents"][0]["parts"])
        except (KeyError, IndexError, TypeError):
            parts = []
        prompt = next((str(part["text"]) for part in parts if isinstance(part, dict) and "text" in part), "")
        sent = next((part["inlineData"] for part in parts if isinstance(part, dict) and "inlineData" in part), None)
        with self.lock:
            self.image_gen_prompts.append(prompt)
            calls = len(self.image_gen_prompts)
            if sent is not None:
                with Image.open(io.BytesIO(base64.b64decode(sent["data"]))) as photo:
                    self.image_edit_requests.append({"prompt": prompt, "size": photo.size})
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

    def _cf_inpaint(self, authorization: str | None, body: dict) -> tuple[int, dict | bytes]:
        with (
            Image.open(io.BytesIO(bytes(body.get("image") or []))) as image,
            Image.open(io.BytesIO(bytes(body.get("mask") or []))) as mask,
        ):
            sizes = {"image": image.size, "mask": mask.size}
        with self.lock:
            self.cf_inpaint_requests.append({"prompt": str(body.get("prompt") or ""), **sizes})
        if authorization != f"Bearer {IMAGE_GEN_CF_KEY}":
            return 401, {
                "result": None,
                "success": False,
                "errors": [{"code": 10000, "message": "Authentication error"}],
            }
        if self.cf_inpaint_mode == "error500":
            return 500, {
                "result": None,
                "success": False,
                "errors": [{"code": 7000, "message": "Internal server error"}],
            }
        if self.cf_inpaint_mode == "quota":
            message = "you have used up your daily free allocation of 10,000 neurons"
            return 429, {"result": None, "success": False, "errors": [{"code": 4006, "message": message}]}
        buffer = io.BytesIO()
        Image.new("RGB", (body.get("width") or 512, body.get("height") or 512), CF_INPAINT_COLOR).save(buffer, "PNG")
        return 200, buffer.getvalue()

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

    def _page_post(self, page: str, edge: str, form: dict, photo: bytes | None) -> tuple[int, dict]:
        """POST /{page-id}/feed (text) or /{page-id}/photos (multipart, the photo as `source`)."""
        if form.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        if page != FACEBOOK_PAGE:
            return 400, {"error": {"message": "Unknown page", "code": 100}}
        with self.lock:
            self.page_post_calls += 1
            if self.page_post_refusals:
                self.page_post_refusals -= 1
                return 400, {"error": {"message": "Invalid parameter", "code": 100}}
            post_id = f"{FACEBOOK_PAGE}_{9000 + len(self.page_posts)}"
            scheduled = form.get("scheduled_publish_time")
            self.page_posts[post_id] = {
                "message": form.get("message", ""),
                "published": form.get("published", "true") != "false",
                "scheduled": int(scheduled) if scheduled else None,
                "photo": photo,
                "edge": edge,
            }
            if self.page_post_replies_lost:
                self.page_post_replies_lost -= 1
                return 500, {"error": {"message": "Service unavailable", "code": 2}}
        if edge == "photos":
            return 200, {"id": f"photo_{post_id}", "post_id": post_id}
        return 200, {"id": post_id}

    def _page_feed(self, edge: str, query: dict) -> tuple[int, dict]:
        """GET /{page-id}/feed (published posts) or /{page-id}/scheduled_posts, newest first."""
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        want = edge == "feed"
        with self.lock:
            data = [
                {"id": post_id, "message": post["message"]}
                for post_id, post in reversed(self.page_posts.items())
                if post["published"] == want
            ]
        return 200, {"data": data}

    def _page_post_read(self, post_id: str, query: dict) -> tuple[int, dict]:
        """GET /{post-id}: its status, or its shares, reactions and comments counts."""
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        post = self.page_posts[post_id]
        if "is_published" in query.get("fields", ""):
            reply = {"id": post_id, "is_published": post["published"]}
            if post["scheduled"]:
                reply["scheduled_publish_time"] = post["scheduled"]
            return 200, reply
        numbers = self.page_post_numbers.get(post_id, DEFAULT_ARTICLE_NUMBERS)
        reply = {
            "id": post_id,
            "reactions": {"data": [], "summary": {"total_count": numbers["reactions"]}},
            "comments": {"data": [], "summary": {"total_count": numbers["comments"]}},
        }
        if numbers["shares"]:
            reply["shares"] = {"count": numbers["shares"]}
        return 200, reply

    def _page_post_insights(self, post_id: str, query: dict) -> tuple[int, dict]:
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        if self.page_post_reach_retired or query.get("metric") != "post_total_media_view_unique":
            return 400, {"error": {"message": "(#100) The value must be a valid insights metric", "code": 100}}
        reach = self.page_post_numbers.get(post_id, DEFAULT_ARTICLE_NUMBERS)["reach"]
        metric = {"name": "post_total_media_view_unique", "period": "lifetime", "values": [{"value": reach}]}
        return 200, {"data": [metric]}

    def _speech_to_text(self, key: str | None, content_type: str, raw: bytes) -> tuple[int, dict]:
        message = BytesParser(policy=email_policy.default).parsebytes(
            f"Content-Type: {content_type}\r\n\r\n".encode() + raw
        )
        fields = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
        with self.lock:
            self.stt_requests.append(
                {
                    "model_id": fields["model_id"].get_content() if "model_id" in fields else None,
                    "bytes": len(fields["file"].get_payload(decode=True) or b"") if "file" in fields else 0,
                }
            )
        if key != ELEVENLABS_KEY:
            return 401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}
        if self.stt_mode == "quota":
            return 401, {"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota"}}
        if self.stt_mode == "no_permission":
            return 401, {
                "detail": {
                    "type": "authentication_error",
                    "code": "unauthorized",
                    "message": "The API key you used is missing the permission speech_to_text to execute this "
                    "operation.",
                    "status": "missing_permissions",
                }
            }
        text = " ".join(word["text"] for word in self.stt_words)
        return 200, {"language_code": "vie", "language_probability": 0.97, "text": text, "words": self.stt_words}

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
        """GET /{page-id}?fields=name,followers_count,picture with the Page's own token."""
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        if self.facebook_page_info_refused:
            return 403, {"error": {"message": "(#200) Requires pages_read_engagement permission", "code": 200}}
        page = next(page for page in self.facebook_pages if page["id"] == page_id)
        reply = {"id": page_id, "name": page["name"]}
        if self.facebook_followers is not None:
            reply["followers_count"] = self.facebook_followers
        if self.facebook_picture is not None:
            reply["picture"] = {"data": {"url": self.facebook_picture, "is_silhouette": False}}
        return 200, reply

    def add_visitor_comment(self, object_id: str, message: str, author: str = "Cô Lan", **fields) -> str:
        """A comment a visitor wrote under a reel (or under a comment, as a reply)."""
        with self.lock:
            comment_id = f"{object_id}_{len(self.facebook_comments) + 1}"
            self.facebook_comments[comment_id] = {
                "object": object_id,
                "message": message,
                "from": {"id": f"user-{len(self.facebook_comments)}", "name": author},
                "edits": 0,
                "hidden": False,
                "created_time": "2026-11-03T07:00:00+0000",
                **fields,
            }
        return comment_id

    def _comment(self, object_id: str, form: dict, create: bool) -> tuple[int, dict]:
        """POST /{reel-id}/comments or /{comment-id}/comments as the Page; POST /{comment-id} edits or hides one."""
        if form.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        with self.lock:
            if self.facebook_comment_refused:
                return 403, {"error": {"message": "(#200) Permissions error", "code": 200}}
            if not create:
                comment = self.facebook_comments[object_id]
                if form.get("is_hidden") == "true":
                    comment["hidden"] = True
                else:
                    comment["message"], comment["edits"] = form["message"], comment["edits"] + 1
                return 200, {"success": True}
            if (
                object_id not in self.reels
                and object_id not in self.facebook_comments
                and object_id not in self.page_posts
            ):
                return 400, {"error": {"message": "Unsupported post request", "code": 100, "error_subcode": 33}}
            comment_id = f"{object_id}_{len(self.facebook_comments) + 1}"
            page = self.facebook_pages[0]
            self.facebook_comments[comment_id] = {
                "object": object_id,
                "message": form["message"],
                "from": {"id": page["id"], "name": page["name"]},
                "edits": 0,
                "hidden": False,
                "created_time": "2026-11-03T07:00:00+0000",
            }
            if self.facebook_comment_replies_lost:
                self.facebook_comment_replies_lost -= 1
                return 500, {"error": {"message": "An unknown error occurred", "code": 1}}
        return 200, {"id": comment_id}

    def _comments(self, object_id: str, query: dict) -> tuple[int, dict]:
        """GET /{id}/comments, newest first, each with its replies' authors as `comments`."""
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        with self.lock:
            if self.facebook_comment_refused:
                return 403, {"error": {"message": "(#200) Permissions error", "code": 200}}
            if object_id in self.facebook_comments_unreadable or (self.reels.get(object_id) or {}).get("lost"):
                return 400, {
                    "error": {
                        "message": f"Unsupported get request. Object with ID '{object_id}' does not exist, cannot be "
                        "loaded due to missing permissions, or does not support this operation.",
                        "code": 100,
                        "error_subcode": 33,
                    }
                }

            def shown(comment_id: str, comment: dict) -> dict:
                replies = [
                    {"id": reply_id, "from": {"id": reply["from"]["id"]}}
                    for reply_id, reply in self.facebook_comments.items()
                    if reply["object"] == comment_id
                ]
                return {
                    "id": comment_id,
                    "message": comment["message"],
                    "from": comment["from"],
                    "created_time": comment["created_time"],
                    "is_hidden": comment["hidden"],
                    "comments": {"data": replies},
                }

            found = [
                shown(comment_id, comment)
                for comment_id, comment in reversed(self.facebook_comments.items())
                if comment["object"] == object_id
            ]
        return 200, {"data": found}

    def _page_insights(self, page_id: str, query: dict) -> tuple[int, dict]:
        """GET /{page-id}/insights?metric=...&period=day, in the shape Meta documents."""
        if query.get("access_token") != FACEBOOK_TOKEN:
            return 400, {"error": {"message": "Invalid OAuth access token", "code": 190}}
        metric = query.get("metric", "")
        if self.facebook_page_insights_refused:
            return 403, {"error": {"message": "(#200) Requires read_insights permission", "code": 200}}
        if metric in self.facebook_page_metrics_dropped or metric not in self.facebook_page_insights:
            return 400, {"error": {"message": "(#100) The value must be a valid insights metric", "code": 100}}
        values = [{"value": value, "end_time": end} for end, value in self.facebook_page_insights[metric].items()]
        return 200, {
            "data": [{"name": metric, "period": "day", "values": values, "id": f"{page_id}/insights/{metric}"}]
        }

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
            asked = set(query.get("metric", "").split(","))
            if asked & self.facebook_retired_metrics:
                return 400, {"error": {"message": "(#100) The value must be a valid insights metric", "code": 100}}
            numbers = self.facebook_insights.get(video_id, DEFAULT_REEL_NUMBERS)

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
        # Meta's names for the rest of the reel's numbers; the retention curve is a breakdown by segment.
        for key, name in (
            ("plays", "blue_reels_play_count"),
            ("replays", "fb_reels_replay_count"),
            ("reach", "post_impressions_unique"),
            ("avg_watch_ms", "post_video_avg_time_watched"),
            ("view_time_ms", "post_video_view_time"),
            ("followers", "post_video_followers"),
            ("retention", "post_video_retention_graph"),
        ):
            if key in numbers:
                data.append(metric(name, numbers[key]))
        # Like Meta, only the metrics asked for come back.
        return 200, {"data": [item for item in data if item["name"] in asked]}

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
            return GONE
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
            if self.reels.pop(video_id, None) is None and self.page_posts.pop(video_id, None) is None:
                return GONE
        return 200, {"success": True}

    def _shopee(self, authorization: str | None, raw: bytes) -> tuple[int, dict]:
        def failed(code: int, message: str) -> tuple[int, dict]:
            return 200, {"errors": [{"message": message, "extensions": {"code": code}}]}

        match = re.fullmatch(r"SHA256 Credential=(\w+), Timestamp=(\d+), Signature=(\w+)", authorization or "")
        if not match or match.group(1) not in self.shopee_apps:
            return failed(10020, "Invalid Authorization Header")
        app_id, timestamp, signature = match.groups()
        payload = raw.decode()
        expected = hashlib.sha256(f"{app_id}{timestamp}{payload}{self.shopee_apps[app_id]}".encode()).hexdigest()
        if signature != expected or abs(time.time() - int(timestamp)) > 600:
            return failed(10020, "Invalid Signature")
        query = json.loads(payload)["query"]
        with self.lock:
            self.shopee_queries.append(query)
        if self.shopee_mode == "rate_limit":
            return failed(10030, "Rate limit exceeded")
        if self.shopee_mode == "error500":
            return 500, {"error": "server"}
        if "productOfferV2" in query:
            item = re.search(r"itemId: (\d+)", query)
            if item:
                item_id = int(item.group(1))
                if item_id in self.shopee_items:
                    node = self.shopee_items[item_id]
                else:
                    # Any other item is offered too, so E2E can paste a product link the fake has never seen.
                    node = next(
                        (n for nodes in self.shopee_offers.values() for n in nodes if n["itemId"] == item_id),
                        shopee_offer(item_id, f"Sản phẩm Shopee {item_id}"),
                    )
                return 200, {"data": {"productOfferV2": {"nodes": [node] if node else []}}}
            keyword = json.loads(re.search(r'keyword: ("(?:[^"\\]|\\.)*")', query).group(1))
            nodes = self.shopee_offers.get(keyword)
            return 200, {"data": {"productOfferV2": {"nodes": default_offers(keyword) if nodes is None else nodes}}}
        if "generateShortLink" in query:
            origin = json.loads(re.search(r'originUrl: ("(?:[^"\\]|\\.)*")', query).group(1))
            sub_ids = json.loads(re.search(r"subIds: (\[[^\]]*\])", query).group(1))
            link = f"https://s.shopee.vn/fake{len(self.shopee_links) + 1}"
            with self.lock:
                self.shopee_links.append({"origin": origin, "sub_ids": sub_ids, "link": link})
            return 200, {"data": {"generateShortLink": {"shortLink": link}}}
        if "conversionReport" in query:
            nodes = self.shopee_conversions
            return 200, {"data": {"conversionReport": {"nodes": nodes, "pageInfo": {"hasNextPage": False}}}}
        return failed(10010, "Unknown query")

    # --- TikTok ---

    @staticmethod
    def _oembed_default(url: str) -> dict:
        path = urllib.parse.urlsplit(url).path
        if path.startswith("/@") and "/video/" in path:
            return {"title": "Video", "author_unique_id": path[2:].split("/", 1)[0].lower()}
        return {"title": "Video", "author_url": "https://www.youtube.com/@anngon"}

    @staticmethod
    def _tiktok_failed(status: int, code: str, message: str) -> tuple[int, dict]:
        return status, {"error": {"code": code, "message": message, "log_id": "fake-log"}}

    def _tiktok_tokens(self, open_id: str) -> dict:
        with self.lock:
            self.tiktok_token_count += 1
            access = f"tt-access-{self.tiktok_token_count}"
            refresh = f"tt-refresh-{self.tiktok_token_count}"
            self.tiktok_access[access] = open_id
            self.tiktok_refresh[refresh] = open_id
        return {
            "open_id": open_id,
            "scope": "user.info.basic,video.upload,video.publish",
            "access_token": access,
            "expires_in": self.tiktok_expires_in,
            "refresh_token": refresh,
            "refresh_expires_in": 31536000,
            "token_type": "Bearer",
        }

    def _tiktok_token(self, form: dict) -> tuple[int, dict]:
        if form.get("client_key") != TIKTOK_CLIENT_KEY or form.get("client_secret") != TIKTOK_CLIENT_SECRET:
            return 200, {"error": "invalid_client", "error_description": "Client key or secret is wrong"}
        if form.get("grant_type") == "authorization_code":
            open_id = self.tiktok_codes.get(form.get("code", ""))
            if open_id is None or not form.get("redirect_uri"):
                return 200, {"error": "invalid_grant", "error_description": "Authorization code is expired."}
            return 200, self._tiktok_tokens(open_id)
        if form.get("grant_type") == "refresh_token":
            with self.lock:
                # TikTok rotates the refresh token: the one just used stops working.
                open_id = self.tiktok_refresh.pop(form.get("refresh_token", ""), None)
            if open_id is None:
                return 200, {"error": "invalid_grant", "error_description": "Refresh token is invalid or expired."}
            return 200, self._tiktok_tokens(open_id)
        return 200, {"error": "unsupported_grant_type", "error_description": "grant_type"}

    def _tiktok_revoke(self, form: dict) -> tuple[int, dict]:
        with self.lock:
            self.tiktok_revoked.append(form.get("token", ""))
            self.tiktok_access.pop(form.get("token", ""), None)
        return 200, {}

    def _tiktok_user(self, authorization: str | None) -> str | None:
        return self.tiktok_access.get((authorization or "").removeprefix("Bearer "))

    def _tiktok_api(self, path: str, authorization: str | None, body: dict) -> tuple[int, dict]:
        open_id = self._tiktok_user(authorization)
        if open_id is None:
            return self._tiktok_failed(401, "access_token_invalid", "The access token is invalid or not found.")
        ok = {"code": "ok", "message": "", "log_id": "fake-log"}
        if path == "/v2/post/publish/creator_info/query/":
            user = self.tiktok_users[open_id]
            return 200, {
                "data": {
                    "creator_username": user["username"],
                    "creator_nickname": user["display_name"],
                    "privacy_level_options": list(self.tiktok_privacy_options),
                    "comment_disabled": False,
                    "duet_disabled": False,
                    "stitch_disabled": True,
                    "max_video_post_duration_sec": 600,
                },
                "error": ok,
            }
        if path in ("/v2/post/publish/inbox/video/init/", "/v2/post/publish/video/init/"):
            if self.tiktok_init_error == "rate_limit_exceeded":
                return self._tiktok_failed(429, "rate_limit_exceeded", "Too many requests")
            if self.tiktok_init_error:
                return self._tiktok_failed(403, self.tiktok_init_error, "Refused")
            direct = path == "/v2/post/publish/video/init/"
            post_info = body.get("post_info") or {}
            if direct and post_info.get("privacy_level") not in self.tiktok_privacy_options:
                return self._tiktok_failed(400, "privacy_level_option_mismatch", "privacy_level is not an option")
            if direct and self.tiktok_unaudited and post_info.get("privacy_level") != "SELF_ONLY":
                return self._tiktok_failed(
                    403,
                    "unaudited_client_can_only_post_to_private_accounts",
                    "Please review our integration guidelines at https://developers.tiktok.com/doc/content-sharing-guidelines/",
                )
            with self.lock:
                publish_id = f"v_pub_file~v2-{len(self.tiktok_posts) + 1}"
                self.tiktok_posts[publish_id] = {
                    "mode": "direct" if direct else "draft",
                    "open_id": open_id,
                    "post_info": post_info,
                    "source_info": body.get("source_info") or {},
                    "bytes": 0,
                    "reads": 0,
                }
            upload_url = f"{self.url}/tiktok-upload/{publish_id}"
            return 200, {"data": {"publish_id": publish_id, "upload_url": upload_url}, "error": ok}
        if path == "/v2/post/publish/status/fetch/":
            post = self.tiktok_posts.get(body.get("publish_id", ""))
            if post is None:
                return self._tiktok_failed(400, "invalid_publish_id", "publish_id does not exist")
            size = post["source_info"].get("video_size") or 0
            with self.lock:
                post["reads"] += 1
                reads = post["reads"]
            if post["bytes"] < size:
                status = "PROCESSING_UPLOAD"
            elif reads <= self.tiktok_busy_reads:
                status = "PROCESSING_DOWNLOAD"
            elif self.tiktok_post_fails or post.get("failed"):
                # FAILED is final for that publish_id, as on TikTok.
                post["failed"] = True
                status = "FAILED"
            else:
                status = "PUBLISH_COMPLETE" if post["mode"] == "direct" else "SEND_TO_USER_INBOX"
            data = {"status": status, "uploaded_bytes": post["bytes"]}
            if status == "FAILED":
                data["fail_reason"] = "video_pull_failed"
            return 200, {"data": data, "error": ok}
        return self._tiktok_failed(404, "not_found", "Unknown path")

    def _tiktok_upload(self, publish_id: str, content_range: str, raw: bytes) -> tuple[int, dict]:
        post = self.tiktok_posts.get(publish_id)
        if post is None:
            return 404, {"error": "not found"}
        with self.lock:
            if self.tiktok_upload_fails > 0:
                self.tiktok_upload_fails -= 1
                return 500, {"error": "upload failed"}
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range or "")
        if not match or int(match.group(2)) - int(match.group(1)) + 1 != len(raw):
            return 400, {"error": "bad Content-Range"}
        with self.lock:
            post["bytes"] += len(raw)
        complete = post["bytes"] >= int(match.group(3))
        return (201 if complete else 206), {}

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
                if path.startswith("/facebook/") and path.endswith("/photos"):
                    message = BytesParser(policy=email_policy.default).parsebytes(
                        f"Content-Type: {self.headers.get('Content-Type', '')}\r\n\r\n".encode() + raw
                    )
                    parts = {
                        part.get_param("name", header="content-disposition"): part for part in message.iter_parts()
                    }
                    form = {name: part.get_content() for name, part in parts.items() if name != "source"}
                    photo = parts["source"].get_payload(decode=True) if "source" in parts else None
                    self._send(*fake._page_post(path.split("/")[2], "photos", form, photo))
                    return
                if path.startswith("/facebook/") and path.endswith("/feed"):
                    form = dict(urllib.parse.parse_qsl(raw.decode()))
                    self._send(*fake._page_post(path.split("/")[2], "feed", form, None))
                    return
                if path.startswith("/facebook/") and path.endswith("/comments"):
                    form = dict(urllib.parse.parse_qsl(raw.decode()))
                    self._send(*fake._comment(path.removeprefix("/facebook/").removesuffix("/comments"), form, True))
                    return
                if path.startswith("/facebook/") and path.removeprefix("/facebook/") in fake.facebook_comments:
                    form = dict(urllib.parse.parse_qsl(raw.decode()))
                    self._send(*fake._comment(path.removeprefix("/facebook/"), form, False))
                    return
                if path.startswith("/facebook/"):
                    form = dict(urllib.parse.parse_qsl(raw.decode()))
                    self._send(*fake._reels_call(path.split("/")[2], form))
                    return
                if path == "/openverse/v1/auth_tokens/token/":
                    form = dict(urllib.parse.parse_qsl(raw.decode()))
                    self._send(*fake._openverse_token(form))
                    return
                if path == "/v1/speech-to-text":
                    self._send(
                        *fake._speech_to_text(self.headers.get("xi-api-key"), self.headers.get("Content-Type", ""), raw)
                    )
                    return
                if path == "/shopee/graphql":
                    self._send(*fake._shopee(self.headers.get("Authorization"), raw))
                    return
                if path.startswith("/tiktok/"):
                    target = path.removeprefix("/tiktok")
                    with fake.lock:
                        fake.tiktok_calls.append(target)
                    if target == "/v2/oauth/token/":
                        self._send(*fake._tiktok_token(dict(urllib.parse.parse_qsl(raw.decode()))))
                    elif target == "/v2/oauth/revoke/":
                        self._send(*fake._tiktok_revoke(dict(urllib.parse.parse_qsl(raw.decode()))))
                    else:
                        body = json.loads(raw or b"{}")
                        self._send(*fake._tiktok_api(target, self.headers.get("Authorization"), body))
                    return
                body = json.loads(raw or b"{}")
                if path == "/v1/messages":
                    self._send(*fake._claude(body))
                elif path == "/openai/v1/chat/completions":
                    self._send(*fake._chat(self.headers.get("Authorization"), body))
                elif path.startswith("/gemini/v1beta/models/"):
                    self._send(*fake._image_gen(self.headers.get("x-goog-api-key"), body))
                elif path.startswith("/cloudflare/client/v4/accounts/") and "/ai/run/" in path and "inpaint" in path:
                    status, reply = fake._cf_inpaint(self.headers.get("Authorization"), body)
                    self._send(status, reply, "image/png" if isinstance(reply, bytes) else "application/json")
                elif path.startswith("/cloudflare/client/v4/accounts/") and "/ai/run/" in path:
                    self._send(*fake._cf_image_gen(self.headers.get("Authorization"), body))
                elif path.startswith("/v1/text-to-speech/"):
                    status, reply = fake._tts(
                        path.removeprefix("/v1/text-to-speech/"), self.headers.get("xi-api-key"), body
                    )
                    self._send(status, reply, "audio/mpeg" if isinstance(reply, bytes) else "application/json")
                elif path == "/vieneu/api/v1/audio/speech":
                    status, reply = fake._vieneu_speech(self.headers.get("Authorization"), body)
                    self._send(status, reply, "audio/mpeg" if isinstance(reply, bytes) else "application/json")
                else:
                    self._send(404, {"error": "not found"})

            def do_PUT(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                path = urllib.parse.urlsplit(self.path).path
                if path.startswith("/tiktok-upload/"):
                    publish_id = path.removeprefix("/tiktok-upload/")
                    with fake.lock:
                        fake.tiktok_calls.append("upload")
                    self._send(*fake._tiktok_upload(publish_id, self.headers.get("Content-Range", ""), raw))
                else:
                    self._send(404, {"error": "not found"})

            def do_DELETE(self):
                parts = urllib.parse.urlsplit(self.path)
                if parts.path.startswith("/facebook/"):
                    query = dict(urllib.parse.parse_qsl(parts.query))
                    self._send(*fake._delete_reel(parts.path.removeprefix("/facebook/"), query))
                else:
                    self._send(404, {"error": "not found"})

            def do_HEAD(self):
                path = urllib.parse.urlsplit(self.path).path
                target = fake.shopee_short_links.get(path.removeprefix("/shopee-short/"))
                if path.startswith("/shopee-short/") and target:
                    self.send_response(301)
                    self.send_header("Location", target)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                if parts.path == "/health":
                    self._send(200, {"ok": True})
                elif parts.path == "/v1/voices":
                    self._send(*fake._voices(self.headers.get("xi-api-key")))
                elif parts.path == "/vieneu/api/v1/voices":
                    self._send(*fake._vieneu_voices(dict(urllib.parse.parse_qsl(parts.query))))
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
                    elif target.endswith(("/feed", "/scheduled_posts")):
                        self._send(*fake._page_feed(target.rsplit("/", 1)[1], query))
                    elif target.endswith("/insights") and target.removesuffix("/insights") in fake.page_posts:
                        self._send(*fake._page_post_insights(target.removesuffix("/insights"), query))
                    elif target in fake.page_posts:
                        self._send(*fake._page_post_read(target, query))
                    elif target in {page["id"] for page in fake.facebook_pages}:
                        self._send(*fake._page_info(target, query))
                    elif target.endswith("/insights"):
                        self._send(*fake._page_insights(target.removesuffix("/insights"), query))
                    elif target.endswith("/comments"):
                        self._send(*fake._comments(target.removesuffix("/comments"), query))
                    elif target.endswith("/video_insights"):
                        self._send(*fake._reel_insights(target.removesuffix("/video_insights"), query))
                    else:
                        self._send(*fake._reel_status(target, query))
                elif parts.path in ("/oembed/tiktok", "/oembed/youtube"):
                    url = dict(urllib.parse.parse_qsl(parts.query)).get("url", "")
                    with fake.lock:
                        fake.oembed_calls.append(url)
                        answer = None if url in fake.oembed_gone else fake.oembed.get(url) or fake._oembed_default(url)
                    self._send(200, answer) if answer is not None else self._send(404, {"error": "not found"})
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
                elif parts.path == "/wikimedia/w/api.php":
                    query = dict(urllib.parse.parse_qsl(parts.query))
                    self._send(*fake._wikimedia(query, self.headers.get("User-Agent", "")))
                elif parts.path == "/unsplash/search/photos":
                    query = dict(urllib.parse.parse_qsl(parts.query))
                    self._send(*fake._unsplash(query, self.headers.get("Authorization")))
                elif parts.path.startswith("/unsplash/photos/") and parts.path.endswith("/download"):
                    name = parts.path.removeprefix("/unsplash/photos/").removesuffix("/download")
                    self._send(*fake._unsplash_download(name, self.headers.get("Authorization")))
                elif parts.path == "/tiktok/v2/user/info/":
                    with fake.lock:
                        fake.tiktok_calls.append("/v2/user/info/")
                    open_id = fake._tiktok_user(self.headers.get("Authorization"))
                    if open_id is None:
                        self._send(*fake._tiktok_failed(401, "access_token_invalid", "The access token is invalid."))
                    else:
                        fields = dict(urllib.parse.parse_qsl(parts.query)).get("fields", "").split(",")
                        # Like TikTok: user.info.basic (the app's only user scope) reads these fields; any other
                        # (username needs user.info.profile) is refused for the whole call.
                        if not set(fields) <= TIKTOK_BASIC_FIELDS:
                            self._send(
                                *fake._tiktok_failed(
                                    401, "scope_not_authorized", "The user did not authorize the scope required."
                                )
                            )
                        else:
                            user = {name: value for name, value in fake.tiktok_users[open_id].items() if name in fields}
                            ok = {"code": "ok", "message": "", "log_id": "fake-log"}
                            self._send(200, {"data": {"user": user}, "error": ok})
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
