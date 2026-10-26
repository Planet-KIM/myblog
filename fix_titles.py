"""One-off maintenance script: re-derive the titles of Milkdown posts.

Recomputes every ``milkdown`` post's title from the first meaningful line of
its content (same rule the board router uses when saving) and stores it when
it differs. Run from anywhere with ``python fix_titles.py``; it uses the app's
configured database.
"""
import os
import sys

# Make project root importable when the script is executed directly.
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.database import SessionLocal
from app.models import BoardPost
from app.routers.board.router import extract_title_from_milkdown_top_line


def main():
    """Update stale Milkdown post titles and print each change.

    Prints ``[id] old -> new`` for every changed post and a final
    ``done: scanned=N, changed=M`` summary. Commits only if something
    changed; the session is always closed.
    """
    db = SessionLocal()
    try:
        milkdown_posts = db.query(BoardPost).filter(BoardPost.editor_type == "milkdown").all()
        changed = 0

        for post in milkdown_posts:
            new_title = extract_title_from_milkdown_top_line(post.content_html, post.content)
            if new_title != post.title:
                print(f"[{post.id}] {post.title!r} -> {new_title!r}")
                post.title = new_title
                changed += 1

        if changed:
            db.commit()
        print(f"done: scanned={len(milkdown_posts)}, changed={changed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
