"""Merge the LingXing core and container-loading migration branches."""

from alembic import op  # noqa: F401 - kept for Alembic migration conventions


revision = "0010_merge_lingxing_container"
down_revision = ("0008_lingxing_core_tables", "0009_container_loading_runs")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
