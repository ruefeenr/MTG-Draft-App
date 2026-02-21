"""add is_active flags to groups and cubes

Revision ID: f2a9c3d1b8e4
Revises: 7c6a8f2b4d11
Create Date: 2026-02-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2a9c3d1b8e4"
down_revision = "7c6a8f2b4d11"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tournament_groups", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table("cubes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table("cubes", schema=None) as batch_op:
        batch_op.drop_column("is_active")

    with op.batch_alter_table("tournament_groups", schema=None) as batch_op:
        batch_op.drop_column("is_active")
