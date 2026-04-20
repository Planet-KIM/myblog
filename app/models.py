from datetime import datetime, timezone, timedelta

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
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
    bookmarks = relationship("PostBookmark", back_populates="user", cascade="all, delete-orphan")
    likes = relationship("PostLike", back_populates="user", cascade="all, delete-orphan")
    followed_categories = relationship("CategoryFollow", back_populates="user", cascade="all, delete-orphan")
    followed_authors = relationship(
        "AuthorFollow",
        foreign_keys="AuthorFollow.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )

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

    # 에디터 타입: "milkdown" (기존 마크다운) 또는 "tiptap" (블록 에디터)
    editor_type = Column(String(20), nullable=False, default="milkdown")

    # TipTap 블록 에디터 JSON 데이터
    content_blocks = Column(Text, nullable=True)

    # 화면에 표시할 작성자 (email 또는 닉네임)
    author = Column(String(255), nullable=False)

    # 공개/비공개
    is_private = Column(Boolean, default=False)
    
    # 제목 표시 여부
    show_title = Column(Boolean, default=True)

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

    # ── 태그 관계 ─────────────────────
    tags = relationship("Tag", secondary="post_tags", back_populates="posts")

    # ── 통계 관계 ─────────────────────
    stats = relationship("PostStats", uselist=False, back_populates="post")
    bookmarks = relationship("PostBookmark", back_populates="post", cascade="all, delete-orphan")
    likes_rel = relationship("PostLike", back_populates="post", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<BoardPost id={self.id} title={self.title!r}>"


# ─────────────────────────────
# 태그 모델
# ─────────────────────────────
class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)
    slug = Column(String(50), nullable=False, unique=True, index=True)
    count = Column(Integer, default=0)
    created_at = Column(DateTime, default=now_kst)

    # 이 태그를 가진 포스트들
    posts = relationship("BoardPost", secondary="post_tags", back_populates="tags")

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name={self.name!r}>"


# ─────────────────────────────
# 포스트-태그 연결 테이블
# ─────────────────────────────
class PostTag(Base):
    __tablename__ = "post_tags"

    post_id = Column(Integer, ForeignKey("board_posts.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)
    created_at = Column(DateTime, default=now_kst)


# ─────────────────────────────
# 포스트 통계 모델
# ─────────────────────────────
class PostStats(Base):
    __tablename__ = "post_stats"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("board_posts.id"), unique=True, nullable=False)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    read_time = Column(Integer, default=0)  # seconds
    unique_visitors = Column(Integer, default=0)
    last_viewed_at = Column(DateTime, nullable=True)

    post = relationship("BoardPost", back_populates="stats")

    def __repr__(self) -> str:
        return f"<PostStats post_id={self.post_id} views={self.views}>"


# ─────────────────────────────
# 포스트 북마크 모델
# ─────────────────────────────
class PostBookmark(Base):
    __tablename__ = "post_bookmarks"
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_post_bookmark_user_post"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("board_posts.id"), nullable=False)
    created_at = Column(DateTime, default=now_kst)

    user = relationship("User", back_populates="bookmarks")
    post = relationship("BoardPost", back_populates="bookmarks")


# ─────────────────────────────
# 포스트 좋아요 모델
# ─────────────────────────────
class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_post_like_user_post"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("board_posts.id"), nullable=False)
    created_at = Column(DateTime, default=now_kst)

    user = relationship("User", back_populates="likes")
    post = relationship("BoardPost", back_populates="likes_rel")


# ─────────────────────────────
# 카테고리 팔로우 모델
# ─────────────────────────────
class CategoryFollow(Base):
    __tablename__ = "category_follows"
    __table_args__ = (UniqueConstraint("user_id", "category_id", name="uq_category_follow_user_category"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("board_categories.id"), nullable=False)
    created_at = Column(DateTime, default=now_kst)

    user = relationship("User", back_populates="followed_categories")
    category = relationship("BoardCategory")


# ─────────────────────────────
# 작성자 팔로우 모델
# ─────────────────────────────
class AuthorFollow(Base):
    __tablename__ = "author_follows"
    __table_args__ = (UniqueConstraint("user_id", "author_user_id", name="uq_author_follow_user_author"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=now_kst)

    user = relationship("User", foreign_keys=[user_id], back_populates="followed_authors")
    author = relationship("User", foreign_keys=[author_user_id])


# ─────────────────────────────
# 뉴스레터 구독 모델 (double opt-in)
# ─────────────────────────────
class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, default="pending")  # pending | confirmed | unsubscribed
    verify_token = Column(String(255), nullable=True, unique=True, index=True)
    source = Column(String(50), nullable=True, default="home")
    created_at = Column(DateTime, default=now_kst)
    confirmed_at = Column(DateTime, nullable=True)


# ─────────────────────────────
# 업로드 파일 레지스트리
# ─────────────────────────────
class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 연결 대상: 발행 전에는 draft_id, 발행 후에는 post_id
    post_id       = Column(Integer, ForeignKey("board_posts.id"), nullable=True)
    draft_id      = Column(String(36), nullable=True)

    # 파일 분류: image / document / text / code / archive / video / audio / other
    file_type     = Column(String(20), nullable=False, default="other")

    original_name = Column(String(255), nullable=False)   # 원본 파일명 (user.pdf)
    stored_name   = Column(String(255), nullable=False)   # 저장된 파일명 (uuid.pdf)
    file_path     = Column(String(500), nullable=False)   # 디스크 절대경로
    url           = Column(String(500), nullable=False)   # 서빙 URL

    size_bytes    = Column(Integer, nullable=False, default=0)
    mime_type     = Column(String(100), nullable=False, default="application/octet-stream")

    created_at    = Column(DateTime, default=now_kst)

    user  = relationship("User")
    post  = relationship("BoardPost")

    def __repr__(self) -> str:
        return f"<UploadedFile id={self.id} type={self.file_type!r} name={self.original_name!r}>"


# ─────────────────────────────
# 임시 저장 (Draft) 모델
# ─────────────────────────────
class Draft(Base):
    __tablename__ = "drafts"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)  # JSON string
    category_id = Column(Integer, ForeignKey("board_categories.id"), nullable=True)
    is_private = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now_kst)
    updated_at = Column(DateTime, default=now_kst, onupdate=now_kst)

    user = relationship("User")
