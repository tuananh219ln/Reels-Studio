from pathlib import Path

from conftest import REAL_DOTENV_PATH

from reels_render import env


def test_dotenv_is_read_from_the_repo_root():
    repo_root = Path(__file__).resolve().parents[2]
    assert repo_root / ".env" == REAL_DOTENV_PATH


def write_dotenv(tmp_path, monkeypatch, content: bytes):
    path = tmp_path / ".env"
    path.write_bytes(content)
    monkeypatch.setattr(env, "DOTENV_PATH", path)


def test_dotenv_with_bom_quotes_comments_and_export(tmp_path, monkeypatch):
    content = (
        "﻿OTHER=1\n"
        "# khóa tìm ảnh\n"
        "\n"
        'export PIXABAY_API_KEY = "abc 123"\n'
        "SINGLE='x=y'\n"
        "# PIXABAY_API_KEY=commented-out\n"
    )
    write_dotenv(tmp_path, monkeypatch, content.encode("utf-8"))
    assert env.read_env("OTHER") == "1", "the BOM must not stick to the first name"
    assert env.read_env("PIXABAY_API_KEY") == "abc 123"
    assert env.read_env("SINGLE") == "x=y"
    assert env.read_env("MISSING") == ""


def test_real_environment_variable_wins_over_dotenv(tmp_path, monkeypatch):
    write_dotenv(tmp_path, monkeypatch, b"PIXABAY_API_KEY=from-file\n")
    monkeypatch.setenv("PIXABAY_API_KEY", "from-env")
    assert env.read_env("PIXABAY_API_KEY") == "from-env"


def test_empty_environment_variable_disables_dotenv_key(tmp_path, monkeypatch):
    write_dotenv(tmp_path, monkeypatch, b"PIXABAY_API_KEY=from-file\n")
    monkeypatch.setenv("PIXABAY_API_KEY", "")
    assert env.read_env("PIXABAY_API_KEY") == ""


def test_missing_dotenv_means_no_key():
    assert env.read_env("PIXABAY_API_KEY") == ""
