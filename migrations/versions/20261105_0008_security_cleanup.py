"""security cleanup: author emails, tag indexes, multi-address subscribers

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05 00:00:00.000000

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# app/services/newsletter.py 의 normalize_single_email 과 같은 규칙 (마이그레이션은 앱 코드에 기대지 않는다)
_SINGLE_EMAIL_RE = re.compile(
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
)


def _scrub_author_emails(conn) -> None:
    """Replace account emails stored in ``board_posts.author`` with public names.

    The column is printed on post pages; posts used to store the writer's
    email there. Each such value becomes the writer's handle, or the part of
    the email before ``@`` when the writer has no handle.

    Args:
        conn: The migration's connection.
    """
    rows = conn.execute(sa.text(
        "SELECT p.id, p.author, u.handle FROM board_posts p "
        "LEFT JOIN users u ON u.id = p.user_id WHERE p.author LIKE '%@%'"
    )).fetchall()
    for post_id, author, handle in rows:
        name = handle or (author or "").split("@")[0] or "user"
        conn.execute(sa.text("UPDATE board_posts SET author = :name WHERE id = :id"), {"name": name, "id": post_id})


def _retire_multi_address_subscribers(conn) -> None:
    """Unsubscribe newsletter rows whose email is not exactly one address.

    Such rows (``a@x.org, b@y.org``) came from a subscribe form that accepted
    address lists, so every listed mailbox received mail after only one of
    them confirmed.

    Args:
        conn: The migration's connection.
    """
    rows = conn.execute(sa.text("SELECT id, email FROM newsletter_subscribers")).fetchall()
    for row_id, email in rows:
        normalized = (email or "").strip().lower()
        if len(normalized) > 254 or not _SINGLE_EMAIL_RE.fullmatch(normalized):
            conn.execute(
                sa.text("UPDATE newsletter_subscribers SET status = 'unsubscribed', verify_token = NULL WHERE id = :id"),
                {"id": row_id},
            )


def upgrade() -> None:
    """Index tag lookups and clean up data written by the old, unsafe code.

    Adds ``post_tags(tag_id)`` and ``tags(count)`` indexes (tag counts and the
    popular-tag lists scanned whole tables), takes account emails out of
    ``board_posts.author`` and unsubscribes multi-address newsletter rows.
    """
    with op.batch_alter_table('post_tags', schema=None) as batch_op:
        batch_op.create_index('ix_post_tags_tag_id', ['tag_id'], unique=False)
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.create_index('ix_tags_count', ['count'], unique=False)

    conn = op.get_bind()
    _scrub_author_emails(conn)
    _retire_multi_address_subscribers(conn)


def downgrade() -> None:
    """Drop the two indexes. The data cleanup is not undone."""
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_index('ix_tags_count')
    with op.batch_alter_table('post_tags', schema=None) as batch_op:
        batch_op.drop_index('ix_post_tags_tag_id')
