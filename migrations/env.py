import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config
from main.models.base import Base

# Import all models to ensure they are registered with Base.metadata
import main.models.user
import main.models.prometheus
import main.models.stocksapi_key

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    context.configure(
        url=f"mysql+pymysql://{Config.MYSQL['USER_USER']}:{Config.MYSQL['USER_PASSWORD']}@{Config.MYSQL['USER_HOST']}/{Config.MYSQL['USER_DATABASE']}",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = f"mysql+pymysql://{Config.MYSQL['USER_USER']}:{Config.MYSQL['USER_PASSWORD']}@{Config.MYSQL['USER_HOST']}/{Config.MYSQL['USER_DATABASE']}"
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
