"""Adopt existing tables without destroying data; create missing service tables."""
from alembic import op
from sqlalchemy import DateTime, inspect
from shared.database import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind, checkfirst=True)
    inspector = inspect(bind)
    # Legacy SQL init used naive UTC timestamps, while ORM writes aware values.
    for table in Base.metadata.sorted_tables:
        actual = {column["name"]: column for column in inspector.get_columns(table.name)}
        for column in table.columns:
            previous = actual.get(column.name)
            if previous and isinstance(column.type, DateTime) and column.type.timezone and isinstance(previous["type"], DateTime) and not previous["type"].timezone:
                op.alter_column(table.name, column.name, type_=DateTime(timezone=True), postgresql_using=f'"{column.name}" AT TIME ZONE \'UTC\'')


def downgrade():
    raise RuntimeError("Destructive downgrade is intentionally unsupported; restore a database backup.")
