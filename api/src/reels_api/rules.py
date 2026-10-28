"""Input rules shared by the HTTP API and the CLI, so both accept exactly the same values."""

import re
import unicodedata

MAX_NAME_LENGTH = 60
MIN_PASSWORD_LENGTH = 8

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class RuleError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_email(email: str) -> str:
    return email.strip().lower()


def clean_email(email: str) -> str:
    email = normalize_email(email)
    if not _EMAIL.fullmatch(email):
        raise RuleError("invalid_email", "Email không hợp lệ")
    return email


def clean_name(name: str) -> str:
    name = unicodedata.normalize("NFC", name).strip()
    if not 1 <= len(name) <= MAX_NAME_LENGTH:
        raise RuleError("invalid_name", f"Tên phải từ 1 đến {MAX_NAME_LENGTH} ký tự")
    return name


def check_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise RuleError("weak_password", f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự")
    return password


def avatar_initial(name: str) -> str:
    # Vietnamese names put the family name first, so the last word tells teammates apart.
    words = unicodedata.normalize("NFC", name).split()
    return words[-1][0].upper() if words else "?"
