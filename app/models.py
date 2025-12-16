from datetime import datetime, timezone, timedelta

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from .database import Base

# ─────────────────────────────
# KST (Asia/Seoul) 시간대
# ─────────────────────────────
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """항상 KST(UTC+9)로 현재 시간을 반환."""
    return datetime.now(KST)


# ─────────────────────────────
# User 모델
# ─────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)

    # 관리자 여부
    is_admin = Column(Boolean, default=False)

    # 사용자가 작성한 게시글들
    posts = relationship("BoardPost", back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


# ─────────────────────────────
# 게시판 카테고리 모델
# (계층 구조: parent_id 로 부모 카테고리 연결)
# ─────────────────────────────
class BoardCategory(Base):
    __tablename__ = "board_categories"

    id = Column(Integer, primary_key=True, index=True)

    # 예: "여행", "공부"
    name = Column(String(100), nullable=False, unique=True)

    # 선택사항: 카테고리 설명
    description = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=now_kst)

    # 🔥 부모 카테고리 (없으면 최상위)
    parent_id = Column(Integer, ForeignKey("board_categories.id"), nullable=True)

    # self-relation
    parent = relationship(
        "BoardCategory",
        remote_side="BoardCategory.id",
        back_populates="children",
    )
    children = relationship(
        "BoardCategory",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    # 이 카테고리에 속한 게시글들
    posts = relationship("BoardPost", back_populates="category")

    def __repr__(self) -> str:
        if self.parent:
            return f"<BoardCategory id={self.id} name={self.name!r} parent={self.parent.name!r}>"
        return f"<BoardCategory id={self.id} name={self.name!r}>"


# ─────────────────────────────
# 게시글 모델
# ─────────────────────────────
class BoardPost(Base):
    __tablename__ = "board_posts"

    id = Column(Integer, primary_key=True, index=True)

    # 제목 (markdown 첫 줄에서 자동 추출)
    title = Column(String(200), nullable=False)

    # markdown 원문
    content = Column(Text, nullable=False)

    # 필요시 사용할 수 있는 미리 렌더링된 HTML
    content_html = Column(Text, nullable=True)

    # 화면에 표시할 작성자 (email 또는 닉네임)
    author = Column(String(255), nullable=False)

    # 공개/비공개
    is_private = Column(Boolean, default=False)

    # ── 카테고리 (서브카테고리 포함) ─────────────────────
    category_id = Column(
        Integer,
        ForeignKey("board_categories.id"),
        nullable=True,
    )
    category = relationship("BoardCategory", back_populates="posts")

    # ── 실제 작성자(User) ─────────────────
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="posts")

    created_at = Column(DateTime, default=now_kst)
    updated_at = Column(
        DateTime,
        default=now_kst,
        onupdate=now_kst,
    )

    def __repr__(self) -> str:
        return f"<BoardPost id={self.id} title={self.title!r}>"
