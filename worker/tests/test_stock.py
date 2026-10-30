import io
import ssl
import tempfile
import urllib.error

import pytest

from conftest import PIXABAY_TEST_KEY, REAL_DEFAULT_CACHE_DIR, REAL_FETCH, jpeg_bytes, make_image, scene, urls
from reels_render import stock
from reels_render.errors import StockSearchError
from reels_render.images import is_image
from reels_render.script import parse_script
from reels_render.stock import HttpStatusError, NetworkError, Pixabay, SearchCache, TooLargeError, find_stock_images


class Rng:
    """Takes a fixed position of each offered pool and records the pools."""

    def __init__(self, position: int = 0):
        self.position = position
        self.pools: list[list[str]] = []

    def choice(self, pool):
        self.pools.append(list(pool))
        return pool[min(self.position, len(pool) - 1)]


@pytest.fixture
def folder(tmp_path):
    make_image(tmp_path / "a.jpg", (40, 40))
    (tmp_path / "work").mkdir()
    return tmp_path


def stock_scene(text: str = "Cá kho tộ\nGiàu *canxi*", **extra) -> dict:
    return scene(text, image="", **extra)


def script_with(*scenes: dict, title: dict | None = None) -> dict:
    return {"title": title or scene(), "scenes": list(scenes)}


def client(folder, now=None, sleeps: list | None = None) -> Pixabay:
    cache = SearchCache(folder / "cache", now=lambda: now[0]) if now else SearchCache(folder / "cache")
    return Pixabay(PIXABAY_TEST_KEY, cache=cache, sleep=sleeps.append if sleeps is not None else lambda seconds: None)


def find(folder, data, *, rng=None, pixabay_client=None, warnings=None):
    return find_stock_images(
        parse_script(data, folder),
        folder / "work",
        on_warning=warnings.append if warnings is not None else None,
        client=pixabay_client,
        rng=rng or Rng(),
    )


def labels(scenes) -> list[str]:
    return [item.label for item in scenes]


class TestChoosingImages:
    def test_scenes_with_their_own_images_need_no_key_and_send_nothing(self, folder):
        result = find(folder, script_with(scene(), scene()))
        assert result.missing == []
        assert result.api_calls == 0
        assert [item.image for item in result.script.all_scenes] == [folder / "a.jpg"] * 3

    def test_search_sends_vietnamese_safe_photo_query_and_downloads_the_large_image(self, folder, pixabay):
        found = urls("ca", 3)
        pixabay.results["Cá kho tộ"] = found
        result = find(folder, script_with(stock_scene()))

        assert pixabay.searches == [
            {
                "key": PIXABAY_TEST_KEY,
                "q": "Cá kho tộ",
                "lang": "vi",
                "image_type": "photo",
                "safesearch": "true",
                "per_page": "10",
            }
        ]
        assert pixabay.downloads == [found[0]]
        image = result.script.scenes[0].image
        assert image.parent == folder / "work"
        assert is_image(image)
        assert result.api_calls == 1

    def test_keywords_are_tried_in_order_until_one_gives_an_image(self, folder, pixabay):
        pixabay.results["cá kho"] = urls("ca", 2)
        result = find(folder, script_with(stock_scene(keywords=["cá kho tộ", "cá kho", "món cá"])))
        assert pixabay.keywords == ["cá kho tộ", "cá kho"]
        assert result.missing == []

    def test_choice_is_among_first_three_unused_results_in_relevance_order(self, folder, pixabay):
        found = urls("ca", 6)
        pixabay.results["cá kho"] = found
        rng = Rng(position=2)
        result = find(folder, script_with(stock_scene(keywords=["cá kho"]), stock_scene(keywords=["cá kho"])), rng=rng)

        assert rng.pools == [found[0:3], [found[0], found[1], found[3]]]
        assert pixabay.downloads == [found[2], found[3]]
        first, second = (item.image for item in result.script.scenes)
        assert first != second
        assert pixabay.keywords == ["cá kho"], "the second scene reuses the cached search"

    def test_unusable_candidates_make_room_for_later_results(self, folder, pixabay):
        found = urls("ca", 5)
        pixabay.results["cá kho"] = found
        pixabay.files[found[0]] = b"not an image"
        pixabay.files[found[1]] = TooLargeError()
        rng = Rng()
        result = find(folder, script_with(stock_scene(keywords=["cá kho"])), rng=rng)

        assert rng.pools == [found[0:3], found[1:4], found[2:5]]
        assert result.missing == []
        assert sorted(path.name for path in (folder / "work").iterdir()) == [result.script.scenes[0].image.name]

    def test_only_the_first_ten_results_are_candidates(self, folder, pixabay):
        found = urls("ca", 12)
        pixabay.results["cá kho"] = found
        for url in found:
            pixabay.files[url] = b"broken"
        result = find(folder, script_with(stock_scene(keywords=["cá kho"])))
        assert sorted(pixabay.downloads) == sorted(found[:10])
        assert labels(result.missing) == ["Cảnh 1"]

    def test_scene_takes_next_keyword_when_results_are_already_used(self, folder, pixabay):
        pixabay.results["sữa chua"] = urls("sua", 1)
        pixabay.results["món ăn"] = urls("mon", 1)
        keywords = ["sữa chua", "món ăn"]
        result = find(folder, script_with(stock_scene(keywords=keywords), stock_scene(keywords=keywords)))
        assert pixabay.downloads == [urls("sua", 1)[0], urls("mon", 1)[0]]
        assert result.script.scenes[0].image != result.script.scenes[1].image

    def test_duplicate_is_reused_when_no_new_image_is_left(self, folder, pixabay):
        pixabay.results["sữa chua"] = urls("sua", 1)
        result = find(folder, script_with(*[stock_scene(keywords=["sữa chua", "sữa"])] * 2))
        assert result.missing == []
        assert result.script.scenes[0].image == result.script.scenes[1].image
        assert len(pixabay.downloads) == 1

    def test_title_without_keywords_is_missing_without_any_search_or_key(self, folder):
        result = find(folder, script_with(scene(), title=scene(image="")))
        assert labels(result.missing) == ["Cảnh tiêu đề"]
        assert result.api_calls == 0

    def test_video_scene_is_never_searched_or_missing(self, folder):
        (folder / "vuon.mp4").write_bytes(b"clip")
        result = find(folder, script_with(scene(), title=scene(image="", video="vuon.mp4", keywords=["rau dền"])))
        assert result.missing == []
        assert result.api_calls == 0

    def test_title_with_keywords_is_searched(self, folder, pixabay):
        pixabay.results["món ăn giàu canxi"] = urls("canxi", 2)
        result = find(folder, script_with(scene(), title=stock_scene("5 MÓN\nCHẮC XƯƠNG", keywords=["món ăn giàu canxi"])))
        assert result.missing == []
        assert pixabay.keywords == ["món ăn giàu canxi"]

    def test_missing_image_file_warns_and_is_replaced_by_a_search(self, folder, pixabay):
        pixabay.results["Vừng đen"] = urls("vung", 1)
        warnings = []
        data = {"title": scene(image="tieu-de.jpg"), "scenes": [scene("Vừng đen\nRắc", image="anh-vung.jpg")]}
        result = find(folder, data, warnings=warnings)

        assert warnings == [
            "Cảnh tiêu đề: không thấy file tieu-de.jpg",
            "Cảnh 1: không thấy file anh-vung.jpg, sẽ tìm ảnh thay thế",
        ]
        assert pixabay.keywords == ["Vừng đen"]
        assert labels(result.missing) == ["Cảnh tiêu đề"]
        assert result.script.scenes[0].image.parent == folder / "work"


class TestDefaults:
    def test_default_client_reuses_the_shared_cache_across_renders(self, folder, pixabay):
        pixabay.results["Cá kho tộ"] = urls("ca", 3)
        data = script_with(stock_scene())
        assert find_stock_images(parse_script(data, folder), folder / "work").api_calls == 1
        assert find_stock_images(parse_script(data, folder), folder / "work").api_calls == 0

    def test_default_choice_is_unseeded_random(self, folder, pixabay, monkeypatch):
        pixabay.results["Cá kho tộ"] = urls("ca", 3)
        seeds = []

        class Recorder(Rng):
            def __init__(self, *args):
                super().__init__()
                seeds.append(args)

        monkeypatch.setattr(stock.random, "Random", Recorder)
        find_stock_images(parse_script(script_with(stock_scene()), folder), folder / "work")
        assert seeds == [()]


class TestCache:
    def test_cache_lives_in_the_system_temp_folder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        assert REAL_DEFAULT_CACHE_DIR() == tmp_path / "reels_render_cache"

    def test_results_are_reused_for_24_hours_then_searched_again(self, folder, pixabay):
        pixabay.results["Cá kho tộ"] = urls("ca", 3)
        now = [1_000_000.0]
        data = script_with(stock_scene())

        assert find(folder, data, pixabay_client=client(folder, now)).api_calls == 1
        now[0] += stock.CACHE_TTL - 1
        cached = find(folder, data, pixabay_client=client(folder, now), rng=Rng(position=1))
        assert cached.api_calls == 0
        assert pixabay.downloads[-1] == urls("ca", 3)[1], "a cached list still follows the top-three rule"
        now[0] += 2
        assert find(folder, data, pixabay_client=client(folder, now)).api_calls == 1

    def test_corrupt_cache_file_means_searching_again(self, folder, pixabay):
        pixabay.results["Cá kho tộ"] = urls("ca", 3)
        data = script_with(stock_scene())
        find(folder, data, pixabay_client=client(folder))
        for path in (folder / "cache").iterdir():
            path.write_text('{"saved_at": "x", "urls": ', encoding="utf-8")
        assert find(folder, data, pixabay_client=client(folder)).api_calls == 1

    def test_unwritable_cache_folder_does_not_stop_the_search(self, folder, pixabay):
        pixabay.results["Cá kho tộ"] = urls("ca", 3)
        (folder / "cache").write_text("a file where the folder should be", encoding="utf-8")
        result = find(folder, script_with(stock_scene()), pixabay_client=client(folder))
        assert result.missing == []
        assert result.api_calls == 1


class TestErrors:
    def test_missing_key_stops_before_any_request(self, folder):
        with pytest.raises(StockSearchError, match="PIXABAY_API_KEY.*\\.env"):
            find(folder, script_with(stock_scene()))

    def test_empty_environment_variable_overrides_key_in_dotenv(self, folder, monkeypatch):
        dotenv = folder / ".env"
        dotenv.write_text("PIXABAY_API_KEY=from-file\n", encoding="utf-8")
        monkeypatch.setattr("reels_render.env.DOTENV_PATH", dotenv)
        monkeypatch.setenv("PIXABAY_API_KEY", "")
        with pytest.raises(StockSearchError, match="PIXABAY_API_KEY"):
            find(folder, script_with(stock_scene()))

    def test_search_recovered_by_retry_is_not_a_network_failure(self, folder, pixabay):
        pixabay.results["xyzqwv"] = (NetworkError("getaddrinfo failed"), [])
        result = find(folder, script_with(stock_scene(keywords=["xyzqwv"])), pixabay_client=client(folder))
        assert labels(result.missing) == ["Cảnh 1"], "the scene is asked, not stopped as a network failure"

    def test_connection_error_is_retried_once_after_5_seconds(self, folder, pixabay):
        pixabay.results["Cá kho tộ"] = (NetworkError("getaddrinfo failed"), urls("ca", 1))
        sleeps = []
        result = find(folder, script_with(stock_scene()), pixabay_client=client(folder, sleeps=sleeps))
        assert sleeps == [5]
        assert result.api_calls == 2
        assert result.missing == []

    @pytest.mark.parametrize(
        ("failure", "message"),
        [
            (NetworkError("getaddrinfo failed"), "Không kết nối được Pixabay"),
            (NetworkError("timed out"), "Không kết nối được Pixabay"),
            (HttpStatusError(429, "API rate limit exceeded"), "giới hạn lượt tìm, thử lại sau 1 phút"),
            (HttpStatusError(500, "Internal Server Error"), "Pixabay đang lỗi \\(HTTP 500\\)"),
            (HttpStatusError(503, "Service Unavailable"), "Pixabay đang lỗi \\(HTTP 503\\)"),
            (TooLargeError(), "Pixabay trả kết quả quá lớn"),
        ],
    )
    def test_search_failing_twice_stops_with_typed_error(self, folder, pixabay, failure, message):
        pixabay.results["Cá kho tộ"] = failure
        sleeps = []
        with pytest.raises(StockSearchError, match=message):
            find(folder, script_with(stock_scene(keywords=["Cá kho tộ", "món cá"])), pixabay_client=client(folder, sleeps=sleeps))
        assert sleeps == [5]
        assert pixabay.keywords == ["Cá kho tộ", "Cá kho tộ"]

    @pytest.mark.parametrize(
        "body", ["[ERROR 400] Invalid API key: abc", "[ERROR 400] Invalid or missing API key (https://pixabay.com/api/docs/)"]
    )
    def test_rejected_key_stops_at_once(self, folder, pixabay, body):
        pixabay.results["Cá kho tộ"] = HttpStatusError(400, body)
        with pytest.raises(StockSearchError, match="^Key Pixabay không hợp lệ, kiểm tra file .env$"):
            find(folder, script_with(stock_scene(keywords=["Cá kho tộ", "món cá"])))
        assert len(pixabay.searches) == 1

    @pytest.mark.parametrize("status", [400, 404])
    def test_other_rejected_keyword_is_skipped_with_warning(self, folder, pixabay, status):
        body = f'[ERROR {status}] "per_page" is out of valid range. https://pixabay.com/api/?key={PIXABAY_TEST_KEY}&q=x'
        pixabay.results["xyz"] = HttpStatusError(status, body)
        pixabay.results["cá kho"] = urls("ca", 1)
        warnings = []
        result = find(folder, script_with(stock_scene(keywords=["xyz", "cá kho"])), warnings=warnings)

        (warning,) = warnings
        assert warning.startswith("Cảnh 1: ") and "xyz" in warning and f"HTTP {status}" in warning
        assert "không hợp lệ" not in warning
        assert PIXABAY_TEST_KEY not in warning
        assert result.missing == []
        assert len(pixabay.searches) == 2

    def test_download_network_failure_moves_to_another_candidate(self, folder, pixabay):
        found = urls("ca", 3)
        pixabay.results["Cá kho tộ"] = found
        pixabay.files[found[0]] = NetworkError("timed out")
        result = find(folder, script_with(stock_scene()))
        assert pixabay.downloads == found[:2]
        assert result.missing == []

    def test_second_download_network_failure_of_a_scene_stops(self, folder, pixabay):
        found = urls("ca", 3)
        pixabay.results["Cá kho tộ"] = found
        pixabay.files[found[0]] = HttpStatusError(403, "Forbidden")
        pixabay.files[found[1]] = NetworkError("connection reset")
        with pytest.raises(StockSearchError, match="Mạng chậm hoặc bị chặn khi tải ảnh"):
            find(folder, script_with(stock_scene()))

    def test_scene_with_a_network_failure_is_never_left_for_the_user(self, folder, pixabay):
        pixabay.results["cá kho"] = urls("ca", 1)
        pixabay.files[urls("ca", 1)[0]] = NetworkError("timed out")
        with pytest.raises(StockSearchError, match="Không tải được ảnh cho Cảnh 1 do lỗi mạng"):
            find(folder, script_with(stock_scene(keywords=["cá kho", "món cá"])))
        assert pixabay.keywords == ["cá kho", "món cá"]

    def test_network_failures_are_counted_per_scene(self, folder, pixabay):
        first, second = urls("a", 2), urls("b", 2)
        pixabay.results["món a"] = first
        pixabay.results["món b"] = second
        pixabay.files[first[0]] = NetworkError("timed out")
        pixabay.files[second[0]] = NetworkError("timed out")
        data = script_with(
            stock_scene(keywords=["món a"]), stock_scene(keywords=["món b"]), stock_scene(keywords=["không có"])
        )
        result = find(folder, data)
        assert labels(result.missing) == ["Cảnh 3"], "a clean scene after recovered failures is still asked"

    def test_search_answer_that_is_not_json_is_a_typed_error(self, folder, pixabay, monkeypatch):
        monkeypatch.setattr(stock, "fetch", lambda url, timeout, max_bytes: b"<html>maintenance</html>")
        with pytest.raises(StockSearchError, match="không đọc được"):
            find(folder, script_with(stock_scene()))

    def test_requests_use_the_15_second_and_15_mb_limits(self, folder, pixabay):
        pixabay.results["Cá kho tộ"] = urls("ca", 1)
        find(folder, script_with(stock_scene()))
        assert pixabay.limits == [
            ("search", 15, stock.MAX_RESPONSE_BYTES),
            ("download", 15, 15 * 1024 * 1024),
        ]

    def test_error_messages_never_contain_the_key(self, folder, pixabay):
        url = f"https://pixabay.com/api/?key={PIXABAY_TEST_KEY}&q=x"
        pixabay.results["Cá kho tộ"] = NetworkError(f"failed for {url} ({PIXABAY_TEST_KEY})")
        with pytest.raises(StockSearchError) as err:
            find(folder, script_with(stock_scene()), pixabay_client=client(folder))
        assert PIXABAY_TEST_KEY not in str(err.value)
        assert "key=***" in str(err.value)

    def test_non_https_result_urls_are_never_fetched(self, folder, pixabay):
        pixabay.results["Cá kho tộ"] = ["file:///etc/passwd", "http://example.com/a.jpg", *urls("ca", 1)]
        find(folder, script_with(stock_scene()))
        assert pixabay.downloads == urls("ca", 1)


class FakeResponse:
    def __init__(self, chunks: list[bytes], headers: dict | None = None, on_read=None):
        self.chunks = list(chunks)
        self.headers = headers or {}
        self.on_read = on_read or (lambda: None)

    def isclosed(self):
        return not self.chunks

    def read1(self, size):
        self.on_read()
        return self.chunks.pop(0) if self.chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestFetch:
    def serve(self, monkeypatch, outcome):
        requests = []

        def urlopen(request, timeout):
            requests.append((request.full_url, request.get_header("User-agent"), timeout))
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        monkeypatch.setattr(stock.urllib.request, "urlopen", urlopen)
        return requests

    def test_connection_dropped_before_content_length_is_a_network_error(self, monkeypatch):
        self.serve(monkeypatch, FakeResponse([b"x" * 10], {"Content-Length": "1000"}))
        with pytest.raises(NetworkError, match="mất kết nối"):
            REAL_FETCH("https://cdn.pixabay.com/a.jpg", 15, 2000)

    def test_each_read_waits_only_for_the_time_left(self, monkeypatch):
        now = [0.0]
        monkeypatch.setattr(stock, "_clock", lambda: now[0])
        timeouts = []

        class Sock:
            def settimeout(self, value):
                timeouts.append(value)

        def slow():
            now[0] += 6

        response = FakeResponse([b"a", b"b", b"c"], on_read=slow)
        response.fp = type("Fp", (), {"raw": type("Raw", (), {"_sock": Sock()})()})()
        self.serve(monkeypatch, response)
        with pytest.raises(NetworkError, match="hết thời gian chờ"):
            REAL_FETCH("https://cdn.pixabay.com/a.jpg", 15, 100)
        assert timeouts == [15, 9, 3]

    def test_sends_its_own_user_agent_and_returns_the_body(self, monkeypatch):
        requests = self.serve(monkeypatch, FakeResponse([b"ab", b"cd"]))
        assert REAL_FETCH("https://cdn.pixabay.com/a.jpg", 15, 100) == b"abcd"
        assert requests == [("https://cdn.pixabay.com/a.jpg", stock.USER_AGENT, 15)]

    @pytest.mark.parametrize(
        "response", [FakeResponse([b"x"], {"Content-Length": "101"}), FakeResponse([b"x" * 60, b"x" * 60])]
    )
    def test_body_over_the_limit_is_too_large(self, monkeypatch, response):
        self.serve(monkeypatch, response)
        with pytest.raises(TooLargeError):
            REAL_FETCH("https://cdn.pixabay.com/a.jpg", 15, 100)

    def test_body_trickling_in_past_the_deadline_is_a_network_error(self, monkeypatch):
        now = [0.0]
        monkeypatch.setattr(stock, "_clock", lambda: now[0])

        def slow():
            now[0] += 4  # each chunk arrives within the socket timeout, but the total exceeds 15 s

        self.serve(monkeypatch, FakeResponse([b"x"] * 10, on_read=slow))
        with pytest.raises(NetworkError, match="hết thời gian chờ"):
            REAL_FETCH("https://cdn.pixabay.com/a.jpg", 15, 100)

    def test_http_error_keeps_status_and_body(self, monkeypatch):
        error = urllib.error.HTTPError("https://pixabay.com/api/", 400, "Bad Request", {}, io.BytesIO(b"[ERROR 400] Invalid API key"))
        self.serve(monkeypatch, error)
        with pytest.raises(HttpStatusError) as err:
            REAL_FETCH("https://pixabay.com/api/", 15, 100)
        assert (err.value.status, err.value.body) == (400, "[ERROR 400] Invalid API key")

    def test_http_error_body_that_cannot_be_read_still_gives_the_status(self, monkeypatch):
        class StalledBody(io.BytesIO):
            def read(self, *args):
                raise TimeoutError("timed out")

        error = urllib.error.HTTPError("https://pixabay.com/api/", 503, "Busy", {}, StalledBody())
        self.serve(monkeypatch, error)
        with pytest.raises(HttpStatusError) as err:
            REAL_FETCH("https://pixabay.com/api/", 15, 100)
        assert (err.value.status, err.value.body) == (503, "")

    @pytest.mark.parametrize(
        "error",
        [
            urllib.error.URLError(ConnectionRefusedError(10061, "refused")),
            urllib.error.URLError(ssl.SSLError(1, "certificate verify failed")),
            TimeoutError("timed out"),
            ConnectionResetError(10054, "reset"),
        ],
    )
    def test_connection_problems_are_network_errors(self, monkeypatch, error):
        self.serve(monkeypatch, error)
        with pytest.raises(NetworkError):
            REAL_FETCH("https://pixabay.com/api/", 15, 100)


def test_download_rejects_bytes_that_are_not_an_image(tmp_path, pixabay):
    pixabay.files["https://cdn.pixabay.com/x.jpg"] = b"<html>not an image</html>"
    pixabay.files["https://cdn.pixabay.com/y.jpg"] = jpeg_bytes()
    downloader = Pixabay(PIXABAY_TEST_KEY, cache=SearchCache(tmp_path / "cache"))
    assert not downloader.download("https://cdn.pixabay.com/x.jpg", tmp_path / "x.img")
    assert downloader.download("https://cdn.pixabay.com/y.jpg", tmp_path / "y.img")
