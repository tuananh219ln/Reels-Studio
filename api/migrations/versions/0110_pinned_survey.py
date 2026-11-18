"""The pinned comment has a fixed shape (docs/decisions/2026-11-19-pinned-comment-fixed-shape.md): the title, the
scenes one per line, then "Dòng khảo sát" (`videos.pinned_survey`), the only part a member types. The old template
(`videos.pinned_comment`) gives each video its survey line: the first line after the one holding `{items}` that has
no variable in it; a template without `{items}`, or with nothing after it, takes the default. The template column is
kept, unread, in case the change has to be undone.

Revision ID: 0110
Revises: 0109
Create Date: 2026-11-19
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None

DEFAULT = "Bạn hay ăn cặp nào nhất? Bình luận số thứ tự nhé"
_VARIABLE = re.compile(r"\{\w+\}")


def survey_of(template: str) -> str:
    lines = (template or "").splitlines()
    at = next((index for index, line in enumerate(lines) if "{items}" in line), None)
    if at is None:
        return DEFAULT
    after = (line.strip() for line in lines[at + 1 :])
    return next((line for line in after if line and not _VARIABLE.search(line)), DEFAULT)


def upgrade() -> None:
    op.add_column("videos", sa.Column("pinned_survey", sa.Text(), nullable=False, server_default=DEFAULT))
    bind = op.get_bind()
    videos = sa.table("videos", sa.column("id", sa.Integer), sa.column("pinned_survey", sa.Text))
    rows = bind.execute(sa.text("SELECT id, pinned_comment FROM videos WHERE pinned_comment LIKE '%{items}%'"))
    for video_id, template in rows.all():
        survey = survey_of(template)
        if survey != DEFAULT:
            bind.execute(sa.update(videos).where(videos.c.id == video_id).values(pinned_survey=survey))


def downgrade() -> None:
    op.drop_column("videos", "pinned_survey")
