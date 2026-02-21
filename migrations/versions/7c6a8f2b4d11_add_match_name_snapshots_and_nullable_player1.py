"""add match name snapshots and nullable player1

Revision ID: 7c6a8f2b4d11
Revises: 1085721ace53
Create Date: 2026-02-18 20:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c6a8f2b4d11"
down_revision = "1085721ace53"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.add_column(sa.Column("player1_name_snapshot", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("player2_name_snapshot", sa.String(length=80), nullable=True))
        batch_op.alter_column("player1_id", existing_type=sa.String(length=36), nullable=True)


def downgrade():
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.alter_column("player1_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.drop_column("player2_name_snapshot")
        batch_op.drop_column("player1_name_snapshot")
