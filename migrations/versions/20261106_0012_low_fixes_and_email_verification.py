"""post list indexes, users.email_verified_at, recounts and card snapshot cleanup

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _recount_likes(conn) -> None:
    """Set every post's like count to its number of likes.

    ``/api/stats/update`` (now removed) let a post's author raise the cached
    count freely.

    Args:
        conn: The migration's connection.
    """
    conn.execute(sa.text(
        "UPDATE post_stats SET likes = (SELECT COUNT(*) FROM post_likes WHERE post_likes.post_id = post_stats.post_id)"
    ))


def _recount_tags(conn) -> None:
    """Set every tag's count to its number of public, visible posts.

    Counts used to include private and moderator-hidden posts, and deleted
    posts were not subtracted.

    Args:
        conn: The migration's connection.
    """
    conn.execute(sa.text(
        "UPDATE tags SET count = (SELECT COUNT(*) FROM post_tags pt JOIN board_posts p ON p.id = pt.post_id "
        "WHERE pt.tag_id = tags.id AND p.is_private = 0 AND (p.is_hidden = 0 OR p.is_hidden IS NULL))"
    ))


def _strip_card_snapshots(conn) -> None:
    """Empty the linked-post card markup saved in post bodies and templates.

    Uses the app's own helpers (``app.services.post_links``), the same ones
    that now run when a post is saved.

    Args:
        conn: The migration's connection.
    """
    from app.services.post_links import strip_card_block_snapshots, strip_card_snapshots

    rows = conn.execute(sa.text(
        "SELECT id, content, content_html, content_blocks FROM board_posts "
        "WHERE content LIKE '%data-post-card=%' OR content_html LIKE '%data-post-card=%' OR content_blocks LIKE '%postcard%'"
    )).fetchall()
    for post_id, content, content_html, blocks in rows:
        conn.execute(
            sa.text("UPDATE board_posts SET content = :c, content_html = :h, content_blocks = :b WHERE id = :id"),
            {"c": strip_card_snapshots(content), "h": strip_card_snapshots(content_html),
             "b": strip_card_block_snapshots(blocks), "id": post_id},
        )
    for tpl_id, blocks in conn.execute(sa.text(
        "SELECT id, content_blocks FROM layout_templates WHERE content_blocks LIKE '%postcard%'"
    )).fetchall():
        conn.execute(sa.text("UPDATE layout_templates SET content_blocks = :b WHERE id = :id"),
                     {"b": strip_card_block_snapshots(blocks), "id": tpl_id})


def upgrade() -> None:
    """Add post list indexes and ``users.email_verified_at``, then fix stored data.

    Indexes ``board_posts(user_id, is_private, created_at)`` and
    ``(is_private, is_hidden, created_at)`` for the blog and public lists.
    ``email_verified_at`` starts NULL for every account (all must verify
    once verification is on). Recounts likes and tags, and empties the
    linked-post card copies saved in bodies.
    """
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_verified_at', sa.DateTime(), nullable=True))
    op.create_index('ix_board_posts_user_private_created', 'board_posts', ['user_id', 'is_private', 'created_at'])
    op.create_index('ix_board_posts_private_hidden_created', 'board_posts', ['is_private', 'is_hidden', 'created_at'])

    conn = op.get_bind()
    _recount_likes(conn)
    _recount_tags(conn)
    _strip_card_snapshots(conn)


def downgrade() -> None:
    """Drop the indexes and the column. The data fixes are not undone."""
    op.drop_index('ix_board_posts_private_hidden_created', table_name='board_posts')
    op.drop_index('ix_board_posts_user_private_created', table_name='board_posts')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email_verified_at')
