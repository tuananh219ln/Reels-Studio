"""Reading a pasted post link (post_links.py): the platform and id, the link written one way, and the text matching
of a post to a video. No database, no network."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from reels_api import post_links
from reels_api.post_links import LinkError, normalize, parse, score, similarity


@pytest.mark.parametrize(
    ("raw", "platform", "external_id", "url"),
    [
        (
            "https://www.tiktok.com/@AnNgon.SongKhoe/video/7301234567890123456?is_from_webapp=1&sender_device=pc",
            "tiktok",
            "7301234567890123456",
            "https://www.tiktok.com/@AnNgon.SongKhoe/video/7301234567890123456",
        ),
        (
            "m.tiktok.com/@an/video/7301234567890",
            "tiktok",
            "7301234567890",
            "https://www.tiktok.com/@an/video/7301234567890",
        ),
        (
            "https://youtube.com/shorts/dQw4w9WgXcQ?si=abc",
            "youtube",
            "dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        ),
        ("https://youtu.be/dQw4w9WgXcQ?si=x", "youtube", "dQw4w9WgXcQ", "https://www.youtube.com/shorts/dQw4w9WgXcQ"),
        (
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share&utm_source=x",
            "youtube",
            "dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        ),
        (
            "https://www.facebook.com/reel/1234567890123",
            "facebook",
            "1234567890123",
            "https://www.facebook.com/reel/1234567890123",
        ),
        (
            "https://www.facebook.com/duongsinh/videos/1234567890123/?mibextid=x",
            "facebook",
            "1234567890123",
            "https://www.facebook.com/duongsinh/videos/1234567890123",
        ),
        (
            "https://www.facebook.com/watch/?v=1234567890123",
            "facebook",
            "1234567890123",
            "https://www.facebook.com/watch/?v=1234567890123",
        ),
    ],
)
def test_a_link_is_read_and_written_one_way(raw, platform, external_id, url):
    link = parse(raw)
    assert (link.platform, link.external_id, link.url) == (platform, external_id, url)


def test_a_tiktok_link_names_its_account_in_lower_case():
    assert parse("https://www.tiktok.com/@AnNgon/video/7301234567890").handle == "anngon"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "không phải link",
        "https://www.tiktok.com/@an",  # a channel, not a post
        "https://www.youtube.com/@anngon",
        "https://youtu.be/short",
        "https://example.com/reel/1234567890",
        "https://www.facebook.com/anngon",
        "ftp://www.tiktok.com/@an/video/7301234567890",
    ],
)
def test_anything_else_is_not_a_post_link(raw):
    with pytest.raises(LinkError) as caught:
        parse(raw)
    assert caught.value.code == "invalid" and caught.value.message == "Link không hợp lệ"


@pytest.mark.parametrize(
    "raw",
    ["https://vt.tiktok.com/ZSabc123/", "https://vm.tiktok.com/ZSabc123/", "https://fb.watch/abcDEF/"],
)
def test_short_links_are_followed_not_parsed(raw):
    assert post_links.is_short(raw)


def test_a_short_link_leading_off_the_platforms_is_refused():
    class Redirect:
        status_code = 302
        headers = {"location": "http://169.254.169.254/latest/meta-data"}

    class Client:
        def get(self, url, follow_redirects):
            return Redirect()

    with pytest.raises(LinkError) as caught:
        post_links.resolve("https://vt.tiktok.com/ZSabc123/", Client())
    assert caught.value.code == "invalid"


def test_a_short_link_is_followed_to_the_post():
    class Redirect:
        status_code = 301
        headers = {"location": "https://www.tiktok.com/@an/video/7301234567890?_r=1"}

    class Client:
        def get(self, url, follow_redirects):
            return Redirect()

    link = post_links.resolve("https://vt.tiktok.com/ZSabc123/", Client())
    assert link.url == "https://www.tiktok.com/@an/video/7301234567890"


def test_text_is_compared_without_marks_hashtags_or_dots_between_letters():
    assert normalize("5 MÓN giúp XƯƠNG chắc khỏe 💪 #suckhoe #anlanh") == "5 mon giup xuong chac khoe"
    assert normalize("Không cần th.uốc!") == "khong can thuoc"
    assert normalize("Đậu đỏ") == "dau do"
    assert similarity("5 món giúp xương chắc khỏe #suckhoe", "5 MÓN GIÚP XƯƠNG CHẮC KHỎE") == 1.0
    assert similarity("cá cơm", "") == 0.0
    assert similarity("rau mầm tốt cho tim", "5 món giúp xương chắc khỏe") < 0.5


def test_score_leaves_out_the_length_when_the_post_has_none():
    published = datetime(2026, 11, 14, tzinfo=UTC)
    video = SimpleNamespace(rendered_at=published - timedelta(days=2), mp4_seconds=30.0)
    # Same words, posted 2 days after the render: full marks with or without the length.
    assert score("5 món giúp xương", published, video, ["5 món giúp xương"]) == pytest.approx(1.0)
    assert score("5 món giúp xương", published, video, ["5 món giúp xương"], duration=30.5) == pytest.approx(1.0)
    # Five seconds off: the length part is lost.
    assert score("5 món giúp xương", published, video, ["5 món giúp xương"], duration=35) == pytest.approx(0.7)
    # Posted 30 days after the render: half of the time part.
    old = SimpleNamespace(rendered_at=published - timedelta(days=30), mp4_seconds=None)
    assert score("5 món giúp xương", published, old, ["5 món giúp xương"]) == pytest.approx((0.6 + 0.05) / 0.7)
