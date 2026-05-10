import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config
from main.models.base import Base
import main.models.user
import main.models.prometheus
import main.models.stocksapi_key

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

targetMetadata = Base.metadata


def getDatabaseUrl() -> str:
    return f"mysql+pymysql://{Config.MYSQL['USER_USER']}:{Config.MYSQL['USER_PASSWORD']}@{Config.MYSQL['USER_HOST']}/{Config.MYSQL['USER_DATABASE']}"


def runMigrationsOffline() -> None:
    context.configure(
        url=getDatabaseUrl(),
        target_metadata=targetMetadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def runMigrationsOnline() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = getDatabaseUrl()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=targetMetadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    runMigrationsOffline()
else:
    runMigrationsOnline()
