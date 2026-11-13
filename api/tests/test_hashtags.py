"""The TikTok caption: the caption text without its trailing Facebook hashtags, then the group's TikTok set."""

from reels_api import hashtags

AN_LANH = "Ăn Lành Sống Khỏe – Sức khỏe"
FB_AN_LANH = "#suckhoe #songkhoe #xuhuong #videoviral #reels #trendingreels #fyp"
TT_AN_LANH = "#suckhoe #songkhoe #anlanh #meosuckhoe"


def test_trailing_tags_are_stripped_inline_and_on_their_own_lines():
    assert hashtags.strip_trailing_tags("Ba món tốt cho tim. #suckhoe #tim") == "Ba món tốt cho tim."
    assert hashtags.strip_trailing_tags("Ba món tốt cho tim\n#suckhoe #tim") == "Ba món tốt cho tim"
    assert hashtags.strip_trailing_tags("Ba món tốt cho tim.") == "Ba món tốt cho tim."
    # "#1" is not a tag, so it stays; only the real tags after it go.
    assert hashtags.strip_trailing_tags("Món #1 #suckhoe") == "Món #1"


def test_the_tiktok_caption_swaps_the_facebook_set_for_the_tiktok_set():
    caption = f"5 sai lầm khi ăn tối khiến cả đêm khó ngủ. Bạn từng mắc sai lầm nào chưa? {FB_AN_LANH}"
    assert hashtags.tiktok_caption(caption, AN_LANH) == (
        "5 sai lầm khi ăn tối khiến cả đêm khó ngủ. Bạn từng mắc sai lầm nào chưa?\n\n" + TT_AN_LANH
    )


def test_the_tiktok_caption_ignores_the_videos_own_hashtag_field():
    # A hand-written script: the caption has no tags, the Facebook set sits in the hashtag field.
    assert hashtags.tiktok_caption("Ba món tốt cho tim", AN_LANH) == f"Ba món tốt cho tim\n\n{TT_AN_LANH}"


def test_a_group_without_a_tiktok_set_gets_the_bare_text():
    caption = (
        "Đứng lên ngồi xuống mà gối kêu lục cục. #suckhoe #duongsinh #songkhoe #videoviral #reels #trendingreels #fyp"
    )
    assert hashtags.tiktok_caption(caption, "Già Mà Khỏe – Dưỡng sinh sau 50") == (
        "Đứng lên ngồi xuống mà gối kêu lục cục."
    )
    assert hashtags.tiktok_caption(caption, None) == "Đứng lên ngồi xuống mà gối kêu lục cục."
