"""Prepare the E2E database: apply migrations, wipe all rows, create the seed user.

Run with DATABASE_URL pointing at reels_e2e (the Playwright global setup does this); it refuses any
other database so it can never wipe dev data.
"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as DbSession

from reels_api.config import database_url
from reels_api.knowledge import default_clone_prompt, default_script_prompt
from reels_api.models import (
    AffiliateAccount,
    AffiliateProduct,
    AppSetting,
    Article,
    EditLog,
    EditTemplate,
    Fanpage,
    Job,
    KnowledgeTopic,
    LlmProvider,
    McpClient,
    MusicTrack,
    Scene,
    Session,
    Setting,
    User,
    Video,
    VideoReference,
)
from reels_api.script_rules import DEFAULT_BANNED_WORDS
from reels_api.security import hash_password

API_DIR = Path(__file__).resolve().parents[1]
SEED = {"email": "an@doi.vn", "name": "Nguyễn Văn An", "password": "mat-khau-dung-1"}


def main() -> int:
    url = database_url()
    if make_url(url).database != "reels_e2e":
        print(f"Từ chối: DATABASE_URL phải trỏ tới reels_e2e (đang là {make_url(url).database})", file=sys.stderr)
        return 1
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    with DbSession(create_engine(url)) as db:
        for model in (
            Job,
            Article,
            Scene,
            Video,
            VideoReference,
            EditLog,
            Fanpage,
            AffiliateProduct,
            AffiliateAccount,
            KnowledgeTopic,
            MusicTrack,
            Setting,
            AppSetting,
            EditTemplate,
            LlmProvider,
            McpClient,
            Session,
            User,
        ):
            db.execute(delete(model))
        db.add(
            User(
                email=SEED["email"],
                name=SEED["name"],
                password_hash=hash_password(SEED["password"]),
                is_active=True,
                must_change_password=False,
            )
        )
        # "Tự tìm ảnh" off: most E2E tests start from scenes without photos; the one about it turns it on.
        db.add(AppSetting(key="auto_photos", value=False))
        db.add(
            KnowledgeTopic(
                name="Sức khỏe",
                script_prompt=default_script_prompt(),
                clone_prompt=default_clone_prompt(),
                banned_words=list(DEFAULT_BANNED_WORDS),
            )
        )
        db.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
