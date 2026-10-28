import pytest
from PIL import Image

from conftest import REAL_FETCH, REAL_PIXABAY_KEY
from reels_render import stock
from reels_render.errors import StockSearchError
from reels_render.stock import Pixabay, SearchCache

pytestmark = pytest.mark.skipif(not REAL_PIXABAY_KEY, reason="không có PIXABAY_API_KEY trong môi trường hay .env")


def test_live_search_and_download_give_a_real_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(stock, "fetch", REAL_FETCH)
    client = Pixabay(REAL_PIXABAY_KEY, cache=SearchCache(tmp_path / "cache"))
    warnings = []
    try:
        found = client.search("sữa chua", "Cảnh 1", warnings.append)
    except StockSearchError as err:
        if "Không kết nối được Pixabay" in str(err):
            pytest.skip(f"không có mạng: {err}")
        raise
    assert found and warnings == []
    target = tmp_path / "photo.img"
    assert client.download(found[0], target)
    with Image.open(target) as image:
        assert max(image.size) >= 640
