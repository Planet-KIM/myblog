"""portal profile and category owner

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06 21:49:28.832381

변경 요약:
  - users: handle/display_name/blog_title/bio/avatar_url 추가 (handle unique)
  - board_categories: user_id(소유자) 추가, 이름 유니크를 전역 → (user_id, name) 복합으로 전환
  - 데이터 백필: 기존 카테고리 소유자 = 최소 user id, 기존 사용자 handle = email local-part(유니크 보장)

SQLite 대응: batch 모드 + naming_convention으로 기존 이름없는 UNIQUE(name)을 안전하게 제거.
"""
from typing import Sequence, Union
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# batch 재생성 시 반영될 제약 이름 규칙 (기존 이름없는 UNIQUE(name)에도 적용됨)
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade() -> None:
    """Add blog profile fields to users and make categories per-owner.

    Adds ``users.handle`` (unique index), ``display_name``, ``blog_title``,
    ``bio`` and ``avatar_url``. Recreates ``board_categories`` with a
    ``user_id`` foreign key to ``users`` (indexed), replacing the global
    ``UNIQUE(name)`` with ``UNIQUE(user_id, name)``. Then backfills data:
    existing categories are assigned to the lowest user id, and each user
    without a handle gets one derived from their email local-part, made
    unique with a numeric suffix (``user<id>`` if nothing usable remains).
    """
    # ── users: 프로필 컬럼 추가 ───────────────────────────
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('handle', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('display_name', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('blog_title', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('bio', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('avatar_url', sa.String(length=500), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_handle'), ['handle'], unique=True)

    # ── board_categories: 소유자 추가 + 유니크 전환 ──────
    # 기존 UNIQUE(name)(이름 없음)을 naming_convention으로 명명해 제거하고,
    # (user_id, name) 복합 유니크로 교체. recreate='always'로 테이블 재생성.
    with op.batch_alter_table(
        'board_categories',
        schema=None,
        naming_convention=NAMING_CONVENTION,
        recreate='always',
    ) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('uq_board_categories_name', type_='unique')
        batch_op.create_index(batch_op.f('ix_board_categories_user_id'), ['user_id'], unique=False)
        batch_op.create_unique_constraint('uq_board_category_owner_name', ['user_id', 'name'])
        batch_op.create_foreign_key(
            'fk_board_categories_user_id_users', 'users', ['user_id'], ['id']
        )

    # ── 데이터 백필 ──────────────────────────────────────
    conn = op.get_bind()

    # 1) 기존 카테고리 소유자 = 가장 낮은 user id (단일 운영자 가정)
    conn.execute(sa.text(
        "UPDATE board_categories SET user_id = (SELECT MIN(id) FROM users) "
        "WHERE user_id IS NULL AND EXISTS (SELECT 1 FROM users)"
    ))

    # 2) 기존 사용자 handle 생성 (email local-part 기반, 유니크 보장)
    rows = conn.execute(
        sa.text("SELECT id, email FROM users WHERE handle IS NULL OR handle = ''")
    ).fetchall()
    used = {
        r[0] for r in conn.execute(
            sa.text("SELECT handle FROM users WHERE handle IS NOT NULL AND handle != ''")
        ).fetchall()
    }
    for uid, email in rows:
        base = re.sub(r'[^a-z0-9_-]', '', (email or '').split('@')[0].lower()).strip('-_')
        base = base[:24] or f"user{uid}"
        candidate = base
        n = 1
        while (not candidate) or candidate in used:
            n += 1
            candidate = f"{base}{n}"[:30]
        used.add(candidate)
        conn.execute(
            sa.text("UPDATE users SET handle = :h WHERE id = :id"),
            {"h": candidate, "id": uid},
        )


def downgrade() -> None:
    """Revert to global category names and drop the user profile columns.

    Recreates ``board_categories`` without ``user_id`` (and its foreign key
    and index), restoring ``UNIQUE(name)``; this fails if two owners have a
    category with the same name. Then drops the ``handle`` index and the
    ``avatar_url``, ``bio``, ``blog_title``, ``display_name`` and ``handle``
    columns from ``users``. Backfilled values are lost.
    """
    # board_categories: 복합 유니크 → 전역 name 유니크 복원
    with op.batch_alter_table(
        'board_categories',
        schema=None,
        naming_convention=NAMING_CONVENTION,
        recreate='always',
    ) as batch_op:
        batch_op.drop_constraint('fk_board_categories_user_id_users', type_='foreignkey')
        batch_op.drop_constraint('uq_board_category_owner_name', type_='unique')
        batch_op.drop_index(batch_op.f('ix_board_categories_user_id'))
        batch_op.create_unique_constraint('uq_board_categories_name', ['name'])
        batch_op.drop_column('user_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_handle'))
        batch_op.drop_column('avatar_url')
        batch_op.drop_column('bio')
        batch_op.drop_column('blog_title')
        batch_op.drop_column('display_name')
        batch_op.drop_column('handle')
