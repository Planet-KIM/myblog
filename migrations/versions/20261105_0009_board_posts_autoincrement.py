"""board_posts AUTOINCREMENT, and rows left behind by deleted posts

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-05 01:00:00.000000

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 다른 행·본문이 글 번호를 가리키는 곳 (삭제된 글의 번호를 찾는 데 쓴다)
_POST_ID_COLUMNS = (
    ("notifications", "post_id"),
    ("comments", "post_id"),
    ("uploaded_files", "post_id"),
    ("post_tags", "post_id"),
    ("post_stats", "post_id"),
    ("post_likes", "post_id"),
    ("post_bookmarks", "post_id"),
)
# 본문 속 글 링크(/board/12)와 연결 카드("postId": 12)
_BODY_POST_ID_RE = re.compile(r'/board/(\d+)|"postId"\s*:\s*"?(\d+)')
# 사용자가 마음대로 적는 번호(본문 링크, 신고 대상)는 서버가 부여한 번호보다 이만큼 위까지만 믿는다.
# 그보다 큰 값을 받아들이면 카운터가 최댓값 근처로 올라가 새 글을 만들 수 없게 될 수 있다.
_USER_ID_MARGIN = 1000


def _highest_post_id_ever(conn) -> int:
    """Return the highest post id that has been given out, as far as the database shows.

    Deleted posts leave their ids in other tables and in links inside post
    bodies; the new AUTOINCREMENT counter must start above them, or the next
    post could take one of those ids. Ids the server wrote (posts and the
    rows tied to them) are trusted. Ids users typed (links in bodies, report
    targets) only count up to ``_USER_ID_MARGIN`` above those, so a planted
    huge number cannot push the counter to its limit.

    Args:
        conn: The migration's connection.

    Returns:
        The largest id found, 0 when there is none.
    """
    highest = conn.execute(sa.text("SELECT COALESCE(MAX(id), 0) FROM board_posts")).scalar() or 0
    for table, column in _POST_ID_COLUMNS:
        value = conn.execute(sa.text(f"SELECT COALESCE(MAX({column}), 0) FROM {table}")).scalar() or 0
        highest = max(highest, value)

    ceiling = highest + _USER_ID_MARGIN
    typed = [row[0] for row in conn.execute(sa.text("SELECT target_id FROM reports WHERE target_type = 'post'"))]
    for row in conn.execute(sa.text("SELECT content, content_html, content_blocks FROM board_posts")):
        for text in row:
            typed += [int(link or card) for link, card in _BODY_POST_ID_RE.findall(text or "")]
    return max([highest] + [n for n in typed if n is not None and n <= ceiling])


def _delete_orphans(conn) -> None:
    """Delete the rows of posts that no longer exist.

    Post deletion used to leave notifications, hidden comments and reports
    behind (SQLite does not enforce the foreign keys here), and they would
    have attached to whichever post got the id next. The other post-id
    tables are swept too, in case an older deletion missed them.

    Args:
        conn: The migration's connection.
    """
    missing = "NOT IN (SELECT id FROM board_posts)"
    conn.execute(sa.text(
        f"DELETE FROM reports WHERE (target_type = 'post' AND target_id {missing}) OR "
        f"(target_type = 'comment' AND target_id IN (SELECT id FROM comments WHERE post_id {missing}))"
    ))
    for table, column in _POST_ID_COLUMNS:
        conn.execute(sa.text(f"DELETE FROM {table} WHERE {column} IS NOT NULL AND {column} {missing}"))


def upgrade() -> None:
    """Stop SQLite from reusing deleted post ids.

    Rebuilds ``board_posts`` with ``AUTOINCREMENT`` (batch mode copies the
    rows, ids included), starts the counter above every id that a row or a
    post body still refers to, and deletes the rows that deleted posts left
    behind. Other databases never reuse ids, so they are left alone.
    """
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return
    highest = _highest_post_id_ever(conn)
    _delete_orphans(conn)
    with op.batch_alter_table(
        'board_posts', schema=None, recreate='always', table_kwargs={'sqlite_autoincrement': True}
    ):
        pass
    if highest:
        updated = conn.execute(
            sa.text("UPDATE sqlite_sequence SET seq = MAX(seq, :n) WHERE name = 'board_posts'"), {"n": highest}
        ).rowcount
        if not updated:
            conn.execute(sa.text("INSERT INTO sqlite_sequence (name, seq) VALUES ('board_posts', :n)"), {"n": highest})


def downgrade() -> None:
    """Rebuild ``board_posts`` without AUTOINCREMENT. Deleted rows are not restored."""
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return
    with op.batch_alter_table(
        'board_posts', schema=None, recreate='always', table_kwargs={'sqlite_autoincrement': False}
    ):
        pass
