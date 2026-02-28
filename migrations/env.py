from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text, MetaData
from alembic import context
import sys
import os

# -----------------------------------------------------
# Path setup: allow importing ingestion_service modules
# -----------------------------------------------------
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

# -----------------------------------------------------
# Import SQLAlchemy Base metadata
# -----------------------------------------------------
from shared.models.base import Base

# -----------------------------------------------------
# Alembic config
# -----------------------------------------------------
config = context.config

# Allow overriding DB URL via env var or `-x db_url=...`
db_url = (
    context.get_x_argument(as_dictionary=True).get("db_url")
    or os.environ.get("DATABASE_URL")
)

if not db_url:
    raise RuntimeError(
        "DATABASE_URL is not set and no -x db_url was provided"
    )

config.set_main_option("sqlalchemy.url", db_url)

# Configure logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata used for autogenerate
target_metadata = Base.metadata
# -----------------------------------------------------
# Environment flags
# -----------------------------------------------------
IS_CI = os.environ.get("CI", "").lower() == "true"

# -----------------------------------------------------
# Offline migrations
# -----------------------------------------------------
def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode (no DB connection).
    Used mainly for autogenerate / SQL output.
    """
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="ingestion_service",
        compare_type=not IS_CI,
        compare_server_default=not IS_CI,
    )

    with context.begin_transaction():
        context.run_migrations()


# -----------------------------------------------------
# Online migrations
# -----------------------------------------------------
def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode (with DB connection).
    This is the normal execution path.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.begin() as connection:
        # Ensure application schema exists
        connection.execute(
            text("CREATE SCHEMA IF NOT EXISTS ingestion_service;")
        )

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="ingestion_service",
            compare_type=not IS_CI,
            compare_server_default=not IS_CI,
        )

        context.run_migrations()


# -----------------------------------------------------
# Entrypoint
# -----------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
