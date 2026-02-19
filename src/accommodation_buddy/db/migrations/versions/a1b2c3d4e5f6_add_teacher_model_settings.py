"""add teacher_model_settings table

Revision ID: a1b2c3d4e5f6
Revises: 6a4c95600e4d
Create Date: 2026-02-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "6a4c95600e4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teacher_model_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "teacher_id",
            sa.Integer(),
            sa.ForeignKey("teachers.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("scaffolding_model", sa.String(255), nullable=True),
        sa.Column("ocr_model", sa.String(255), nullable=True),
        sa.Column("translation_model", sa.String(255), nullable=True),
        sa.Column("keep_alive", sa.String(20), server_default="5m", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("teacher_model_settings")
