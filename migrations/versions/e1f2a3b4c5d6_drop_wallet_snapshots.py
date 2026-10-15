"""drop wallet snapshots

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
Create Date: 2026-10-14 00:00:00.000000

The write-only Snapshot persistence (upserted by /wallet/summary, read
nowhere) is deleted from main/models/wallet.py.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f("ix_snapshots_walletId"), table_name="snapshots")
    op.drop_index(op.f("ix_snapshots_date"), table_name="snapshots")
    op.drop_table("snapshots")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "snapshots",
        sa.Column("snapshotId", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("walletId", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("applied", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("equity", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("variation", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("profitTwr", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("profitAmount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("profitTwr12m", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("profitTwr12mAmount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["walletId"], ["wallets.walletId"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("snapshotId"),
        sa.UniqueConstraint("walletId", "date", name="uq_snapshots_wallet_date"),
    )
    op.create_index(op.f("ix_snapshots_date"), "snapshots", ["date"], unique=False)
    op.create_index(op.f("ix_snapshots_walletId"), "snapshots", ["walletId"], unique=False)
