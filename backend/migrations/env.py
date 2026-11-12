"""Alembic environment. A Postgres advisory lock serializes migrations, so several ECS tasks
starting at once (each runs `alembic upgrade head`) cannot race each other."""
from alembic import context
from sqlalchemy import text

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base, engine

MIGRATION_LOCK_ID = 727274


def run_migrations() -> None:
    with engine.connect() as connection:
        connection.execute(text('SELECT pg_advisory_lock(:id)'), {'id': MIGRATION_LOCK_ID})
        connection.commit()
        try:
            context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(:id)'), {'id': MIGRATION_LOCK_ID})
            connection.commit()


run_migrations()
