import unicodedata

import pytest

from reels_render.markup import MarkupError, Run, normalize_text, parse_scene_text


def test_red_runs_and_manual_lines():
    assert parse_scene_text("Cá nhỏ ăn cả xương\nGiàu *canxi*, rẻ") == [
        [Run("CÁ NHỎ ĂN CẢ XƯƠNG", False)],
        [Run("GIÀU ", False), Run("CANXI", True), Run(", RẺ", False)],
    ]


def test_red_run_may_span_lines():
    assert parse_scene_text("*a\nb* c") == [[Run("A", True)], [Run("B", True), Run(" C", False)]]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Giàu *canxi", "không đóng cặp"),
        ("Giàu * canxi * rẻ *", "không đóng cặp"),
        ("Giàu ** canxi", r"\*\* rỗng"),
        ("Giàu * * canxi", r"\*\* rỗng"),
        ("", "chữ trống"),
        ("   \n  ", "chữ trống"),
        ("Dòng 1\n\nDòng 2", "dòng trống"),
        ("Dòng 1\n", "dòng trống"),
    ],
)
def test_invalid_text(text, message):
    with pytest.raises(MarkupError, match=message):
        parse_scene_text(text)


def test_vietnamese_uppercase():
    assert normalize_text("đậu phụ, rau cải, sữa chua, ưu tiên, vừng đen") == "ĐẬU PHỤ, RAU CẢI, SỮA CHUA, ƯU TIÊN, VỪNG ĐEN"


def test_decomposed_input_becomes_nfc():
    decomposed = unicodedata.normalize("NFD", "tuổi xương chắc khỏe")
    result = normalize_text(decomposed)
    assert result == "TUỔI XƯƠNG CHẮC KHỎE"
    assert unicodedata.is_normalized("NFC", result)
