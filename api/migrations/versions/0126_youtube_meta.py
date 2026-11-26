"""A topic group's "Mô tả YouTube" (`knowledge_topics.youtube_meta`, youtube_meta.py): the YouTube hashtags, keywords,
Subscribe line and disclaimer its uploads carry instead of the Facebook caption.

FoodDose and Topic Threads (Tiệm Đọc Comment, Tôi Đọc Threads) start with a set drawn from the 5 reference Shorts
channels studied on 2026-11-25; their owners edit it on Kho kiến thức. A group missing here (or renamed) starts empty.

Revision ID: 0126
Revises: 0125
Create Date: 2026-11-25
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None

SEED = {
    "FoodDose": {
        "hashtags": [
            "#FoodDose",
            "#Shorts",
            "#HealthTips",
            "#FoodAsMedicine",
            "#HealthyFood",
            "#HealthyEating",
            "#NutritionTips",
            "#Nutrition",
            "#HealthyLiving",
            "#HealthyHabits",
            "#WellnessTips",
            "#HealthyDiet",
            "#HealthFacts",
            "#EatHealthy",
        ],
        "keywords": [
            "food is medicine",
            "healthy foods",
            "health tips",
            "nutrition tips",
            "healthy eating",
            "foods for health",
            "healthy habits",
            "natural health",
            "superfoods",
            "diet tips",
            "everyday health",
            "wellness",
        ],
        "cta": "🔔 Subscribe to {channel} for a daily dose of food and health tips you can use.",
        "disclaimer": (
            "Disclaimer: This video is for general education only and is not medical advice. No single food can cure "
            "or prevent disease. Talk to your doctor or a qualified health professional before changing your diet, "
            "especially if you are pregnant, have a health condition or take medication."
        ),
    },
    "Topic Threads": {
        "hashtags": [
            "#Shorts",
            "#threads",
            "#doccomment",
            "#docthreads",
            "#chuyendoithuong",
            "#tamsu",
            "#giadinh",
            "#honnhan",
            "#cuocsong",
            "#gocnhin",
            "#binhluan",
            "#xuhuong",
        ],
        "keywords": [
            "đọc threads",
            "đọc comment",
            "đọc bình luận",
            "chuyện đời thường",
            "tâm sự",
            "góc nhìn",
            "chuyện gia đình",
            "hôn nhân",
            "cuộc sống",
            "threads việt nam",
        ],
        "cta": "🔔 Đăng ký {channel} để nghe đọc Threads và bình luận hay mỗi ngày.",
        "disclaimer": "",
    },
}


def upgrade() -> None:
    op.add_column("knowledge_topics", sa.Column("youtube_meta", JSONB(), nullable=True))
    bind = op.get_bind()
    for name, meta in SEED.items():
        bind.execute(
            sa.text("UPDATE knowledge_topics SET youtube_meta = CAST(:meta AS jsonb) WHERE name = :name"),
            {"meta": json.dumps(meta, ensure_ascii=False), "name": name},
        )


def downgrade() -> None:
    op.drop_column("knowledge_topics", "youtube_meta")
