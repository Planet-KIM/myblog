import sys
import os

# Set up path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.models import BoardPost
from app.routers.board.router import extract_title_from_markdown

def main():
    db = SessionLocal()
    try:
        posts = db.query(BoardPost).all()
        for post in posts:
            new_title = extract_title_from_markdown(post.content)
            if new_title != post.title:
                print(f"Update [{post.id}] '{post.title}' -> '{new_title}'")
                post.title = new_title
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    main()
