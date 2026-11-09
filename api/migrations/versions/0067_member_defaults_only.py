"""Video defaults are each member's own: members without their own get a copy of the team's, which is then unread

Revision ID: 0067
Revises: 0066
Create Date: 2026-11-09
"""

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # What a member without their own defaults started new videos with until now, so nothing changes for them at the
    # switch. The team's row stays (unread) for a rollback.
    op.execute(
        """
        INSERT INTO user_video_defaults (user_id, value)
        SELECT users.id, app_settings.value
        FROM users JOIN app_settings ON app_settings.key = 'video_defaults'
        WHERE jsonb_typeof(app_settings.value) = 'object'
          AND NOT EXISTS (SELECT 1 FROM user_video_defaults own WHERE own.user_id = users.id)
        """
    )


def downgrade() -> None:
    # The copies cannot be told apart from defaults members saved themselves: they stay, as their own.
    pass
