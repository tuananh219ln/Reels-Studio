from reels_api import config


def use_dotenv(tmp_path, monkeypatch, content: str):
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8-sig")
    monkeypatch.setattr(config, "DOTENV_PATH", path)


def test_dotenv_is_read_from_repo_root_with_bom_quotes_and_export(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    use_dotenv(tmp_path, monkeypatch, "# dev\nexport DATABASE_URL = \"postgresql+psycopg://x@h/db\"\n")
    assert config.database_url() == "postgresql+psycopg://x@h/db"


def test_real_environment_variable_wins_even_when_empty(tmp_path, monkeypatch):
    use_dotenv(tmp_path, monkeypatch, "ALLOWED_ORIGINS=http://from-file\n")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://from-env")
    assert config.allowed_origins() == {"http://from-env"}
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    assert config.allowed_origins() == {"http://localhost:3000"}


def test_allowed_origins_default_and_list(tmp_path, monkeypatch):
    use_dotenv(tmp_path, monkeypatch, "")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert config.allowed_origins() == {"http://localhost:3000"}
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000/, http://localhost:3100")
    assert config.allowed_origins() == {"http://localhost:3000", "http://localhost:3100"}


def test_dotenv_path_is_the_repo_root():
    assert config.DOTENV_PATH == config.Path(__file__).resolve().parents[2] / ".env"


def test_cookie_secure_is_off_unless_enabled(tmp_path, monkeypatch):
    use_dotenv(tmp_path, monkeypatch, "")
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    assert config.cookie_secure() is False
    monkeypatch.setenv("COOKIE_SECURE", "true")
    assert config.cookie_secure() is True
