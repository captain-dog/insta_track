import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from insta_track.config import load_env_file
from insta_track.models import Base

config = context.config
target_metadata = Base.metadata

# When run via the alembic CLI, honour DATABASE_URL from .env like the app does.
load_env_file()
if database_url := os.environ.get("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
