import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from conftest import PASSWORD, make_user
from reels_api.cli import create_or_reset_user
from reels_api.models import Session, User
from reels_api.security import verify_password
from reels_api.sessions import start_session

API_DIR = Path(__file__).resolve().parents[1]


def answers(*values):
    queue = list(values)
    return lambda prompt: queue.pop(0)


def test_new_user_is_active_without_forced_change(db, capsys):
    ask = answers("  Chu@Doi.VN ", "", "  Nguyễn Văn Chủ ")
    secret = answers("ngan", "dung-mat-khau-1", "khac-hoan-toan", "dung-mat-khau-1", "dung-mat-khau-1")

    assert create_or_reset_user(db, ask, secret) == 0

    user = db.scalar(select(User).where(User.email == "chu@doi.vn"))
    assert (user.name, user.is_active, user.must_change_password, user.created_by_id) == (
        "Nguyễn Văn Chủ", True, False, None)
    assert verify_password("dung-mat-khau-1", user.password_hash)
    err = capsys.readouterr().err
    assert "Tên phải từ 1 đến 60 ký tự" in err
    assert "Mật khẩu phải có ít nhất 8 ký tự" in err
    assert "hai lần nhập mật khẩu không khớp" in err


def test_invalid_email_is_asked_again(db, capsys):
    ask = answers("abc", "chu@doi.vn", "Chủ")
    assert create_or_reset_user(db, ask, answers("dung-mat-khau-1", "dung-mat-khau-1")) == 0
    assert "Email không hợp lệ" in capsys.readouterr().err


def test_existing_email_resets_password_reenables_and_signs_out(db):
    user = make_user(db, must_change=True, active=False)
    start_session(db, user)
    db.commit()

    code = create_or_reset_user(db, answers("AN@doi.vn", "c"), answers("khoi-phuc-123", "khoi-phuc-123"))

    assert code == 0
    db.refresh(user)
    assert (user.name, user.is_active, user.must_change_password) == ("Nguyễn Văn An", True, False)
    assert verify_password("khoi-phuc-123", user.password_hash)
    assert db.scalar(select(func.count()).select_from(Session)) == 0


def test_declining_the_reset_changes_nothing(db):
    user = make_user(db, active=False)
    code = create_or_reset_user(db, answers("an@doi.vn", "k"), answers())
    assert code == 1
    db.refresh(user)
    assert user.is_active is False
    assert verify_password(PASSWORD, user.password_hash)


def run_cli(*args):
    result = subprocess.run(
        [sys.executable, "-m", "reels_api", *args],
        input="", capture_output=True, cwd=API_DIR, timeout=60,
        env={**os.environ, "PYTHONIOENCODING": ""},
    )
    return result.returncode, result.stderr.decode("utf-8")


def test_without_a_terminal_it_fails_in_vietnamese_instead_of_hanging():
    code, err = run_cli("create-user")
    assert code == 2
    assert "Lỗi: lệnh này cần chạy trong terminal để nhập mật khẩu ẩn" in err
    assert "Traceback" not in err


@pytest.mark.parametrize("args", [[], ["create_user"]])
def test_unknown_or_missing_command_fails_in_vietnamese(args):
    code, err = run_cli(*args)
    assert code == 2
    assert "Lỗi: lệnh không hợp lệ. Dùng: python -m reels_api create-user" in err
    assert "usage" not in err.lower()
