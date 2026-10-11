"""Migrations run against the connection passed by service lifespan."""
from alembic import context
from shared.database import Base

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Run migrations through the service startup or scripts/migrate.py")
context.configure(connection=connection, target_metadata=Base.metadata,
                  version_table=context.config.attributes["version_table"])
with context.begin_transaction():
    context.run_migrations()
