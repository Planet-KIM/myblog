"""Alembic migration environment.

DB URL과 메타데이터를 앱(app.config / app.models)에서 직접 읽어오므로
로컬(sqlite)·Docker·추후 RDBMS 전환에서 동일하게 동작한다.
SQLite에서는 batch 모드를 켜서 ADD COLUMN/제약 변경 등 ALTER 작업을 지원한다.
"""
from logging.config import fileConfig
import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# 프로젝트 루트를 import 경로에 추가 (app 패키지 로드용)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings          # noqa: E402
from app.database import Base            # noqa: E402
from app import models                   # noqa: E402,F401  (Base.metadata 채우기)

config = context.config

# alembic.ini 의 빈 sqlalchemy.url 을 앱 설정값으로 주입
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _use_batch() -> bool:
    """SQLite는 ALTER 제약이 많아 batch 모드가 필요하다."""
    return settings.DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_use_batch(),
        compare_type=True,
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
            render_as_batch=_use_batch(),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
