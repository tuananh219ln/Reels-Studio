import pytest

from reels_api.rules import RuleError, avatar_initial, check_password, clean_email, clean_name, normalize_email


def test_email_is_trimmed_and_lowercased():
    assert normalize_email("  An.Nguyen@Doi.VN ") == "an.nguyen@doi.vn"
    assert clean_email(" An@Doi.vn") == "an@doi.vn"


@pytest.mark.parametrize("email", ["abc", "an@", "@doi.vn", "an@doi", "an doi@doi.vn", ""])
def test_invalid_email(email):
    with pytest.raises(RuleError) as err:
        clean_email(email)
    assert (err.value.code, err.value.message) == ("invalid_email", "Email không hợp lệ")


def test_name_is_trimmed_before_length_check():
    assert clean_name("  Nguyễn Văn An ") == "Nguyễn Văn An"
    assert clean_name("x" * 60) == "x" * 60


@pytest.mark.parametrize("name", ["", "   ", "x" * 61])
def test_invalid_name(name):
    with pytest.raises(RuleError) as err:
        clean_name(name)
    assert (err.value.code, err.value.message) == ("invalid_name", "Tên phải từ 1 đến 60 ký tự")


def test_password_needs_eight_characters():
    assert check_password("12345678") == "12345678"
    with pytest.raises(RuleError) as err:
        check_password("1234567")
    assert (err.value.code, err.value.message) == ("weak_password", "Mật khẩu phải có ít nhất 8 ký tự")


@pytest.mark.parametrize(
    ("name", "initial"),
    [("Nguyễn Văn An", "A"), ("Nguyễn Văn ánh", "Á"), ("An", "A"), ("  trần   bình  ", "B")],
)
def test_avatar_initial_is_first_letter_of_last_word(name, initial):
    assert avatar_initial(name) == initial


def test_avatar_initial_of_decomposed_vietnamese_text():
    decomposed = "Nguyễn Văn ánh"  # "ánh" typed as a + combining acute accent
    assert avatar_initial(decomposed) == "Á"
