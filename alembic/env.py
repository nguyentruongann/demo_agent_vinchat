"""Cấu hình môi trường Alembic.

URL database lấy từ src.config (đọc .env), KHÔNG hardcode trong alembic.ini —
để không có mật khẩu nào bị commit vào git.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from src.backend.config import get_settings

# Import qua src.data_postgre.db de ca hai metadata deu thay du 41 bang.
from src.data_postgre.db import AppBase, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Hai MetaData vi hai schema: core va app (xem src/data_postgre/db/base.py).
target_metadata = [Base.metadata, AppBase.metadata]

# Chi so sanh hai schema cua ta. Thieu bo loc nay, include_schemas=True se coi
# moi thu ngoai metadata la "thua" va sinh lenh DROP cho ca bang cua extension.
MANAGED_SCHEMAS = {"core", "app"}


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name in MANAGED_SCHEMAS
    return True


def run_migrations_offline() -> None:
    """Sinh SQL ra stdout mà không cần kết nối (alembic upgrade head --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Bắt cả thay đổi kiểu cột và server_default, nếu không autogenerate
            # sẽ bỏ sót khi ta sửa NUMERIC(12,2) hay đổi giá trị mặc định.
            compare_type=True,
            compare_server_default=True,
            include_schemas=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()