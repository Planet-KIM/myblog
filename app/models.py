"""SQLAlchemy ORM models for the blog portal.

Defines users, per-user board categories, posts with tags and stats,
engagement (bookmarks, likes, follows), newsletter subscribers, uploaded
files, drafts, comments, moderation reports, notifications and saved
magazine layout templates. Timestamps default to Korea Standard Time via
``now_kst``.
"""
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
    """A registered account that also owns a personal blog.

    Attributes:
        email: Unique login email.
        password_hash: PBKDF2 hash of the password.
        is_admin: Whether the user can use the admin pages.
        handle: Unique public blog id used in ``/@handle`` URLs (optional).
        display_name, blog_title, bio, avatar_url, cover_url, accent_color:
            Public profile fields shown on the user's blog.
        posts: Posts written by the user.
        bookmarks, likes: The user's bookmarks and likes.
        followed_categories, followed_authors: Categories and authors the
            user follows.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)

    # 관리자 여부
    is_admin = Column(Boolean, default=False)

    # ── 포털 프로필 (블로그 소유자 정보) ─────────────────
    # handle: URL에 노출되는 블로그 식별자 (/@handle). 내부 FK는 항상 id 사용.
    handle = Column(String(30), unique=True, nullable=True, index=True)
    display_name = Column(String(60), nullable=True)   # 표시 이름
    blog_title = Column(String(100), nullable=True)     # 개인 블로그 이름
    bio = Column(String(500), nullable=True)            # 소개
    avatar_url = Column(String(500), nullable=True)     # 프로필 이미지 URL
    cover_url = Column(String(500), nullable=True)      # 블로그 커버(배너) 이미지 URL
    accent_color = Column(String(7), nullable=True)     # 블로그 강조색 (#rrggbb)

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
        """Return a debug representation with id and email."""
        return f"<User id={self.id} email={self.email!r}>"


# ─────────────────────────────
# 게시판 카테고리 모델
# (계층 구조: parent_id 로 부모 카테고리 연결)
# ─────────────────────────────
class BoardCategory(Base):
    """A post category owned by one user, optionally nested under a parent.

    Names are unique per owner, not globally. Deleting a category deletes its
    child categories.

    Attributes:
        name: Category name.
        description: Optional description.
        user_id: Owning user (nullable for legacy rows).
        owner: The owning ``User``.
        parent_id, parent: Parent category, or None for a top-level one.
        children: Direct sub-categories.
        posts: Posts filed in this category.
    """

    __tablename__ = "board_categories"
    # 포털: 카테고리는 블로그(사용자)별 소유. 이름 유니크는 소유자 범위 안에서만.
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_board_category_owner_name"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # 예: "여행", "공부" (전역이 아니라 소유자 내에서 유니크)
    name = Column(String(100), nullable=False)

    # 선택사항: 카테고리 설명
    description = Column(String(255), nullable=True)

    # ── 소유자(블로그 주인) ───────────────────────────────
    # 기존 데이터 호환 위해 nullable. 앞으로 생성 시 항상 채움.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    owner = relationship("User")

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
        """Return a debug representation with id, name and parent name if any."""
        if self.parent:
            return f"<BoardCategory id={self.id} name={self.name!r} parent={self.parent.name!r}>"
        return f"<BoardCategory id={self.id} name={self.name!r}>"


# ─────────────────────────────
# 게시글 모델
# ─────────────────────────────
class BoardPost(Base):
    """A blog post, written in either the Milkdown or the TipTap editor.

    Attributes:
        title: Post title.
        content: Markdown source (or the text form of a block post).
        content_html: Pre-rendered HTML, if any.
        editor_type: ``"milkdown"`` (Markdown) or ``"tiptap"`` (block editor).
        content_blocks: TipTap/magazine block JSON, if any.
        author: Display name of the author.
        is_private: Visible only to the author when True.
        is_hidden: Hidden by moderation; excluded from queries by default.
        show_title: Whether the title is rendered on the post page.
        category_id, category: Optional category.
        user_id, user: The authoring ``User``.
        created_at, updated_at: Timestamps in KST.
        tags: Tags attached through ``post_tags``.
        stats: One-to-one ``PostStats`` row.
        bookmarks, likes_rel, comments: Engagement rows; deleted with the post.
    """

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

    # 관리자 숨김(모더레이션). True면 작성자/관리자 외 비노출.
    is_hidden = Column(Boolean, default=False, nullable=False)

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
    stats = relationship("PostStats", uselist=False, back_populates="post", cascade="all, delete-orphan")
    bookmarks = relationship("PostBookmark", back_populates="post", cascade="all, delete-orphan")
    likes_rel = relationship("PostLike", back_populates="post", cascade="all, delete-orphan")
    comments = relationship(
        "Comment",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="Comment.created_at",
    )

    def __repr__(self) -> str:
        """Return a debug representation with id and title."""
        return f"<BoardPost id={self.id} title={self.title!r}>"


# ─────────────────────────────
# 태그 모델
# ─────────────────────────────
class Tag(Base):
    """A global tag that posts can share.

    Attributes:
        name: Display name (unique).
        slug: URL-safe identifier (unique).
        count: Cached number of posts using the tag.
        posts: Posts carrying the tag.
    """

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)
    slug = Column(String(50), nullable=False, unique=True, index=True)
    count = Column(Integer, default=0)
    created_at = Column(DateTime, default=now_kst)

    # 이 태그를 가진 포스트들
    posts = relationship("BoardPost", secondary="post_tags", back_populates="tags")

    def __repr__(self) -> str:
        """Return a debug representation with id and name."""
        return f"<Tag id={self.id} name={self.name!r}>"


# ─────────────────────────────
# 포스트-태그 연결 테이블
# ─────────────────────────────
class PostTag(Base):
    """Association row linking one post to one tag (table ``post_tags``)."""

    __tablename__ = "post_tags"

    post_id = Column(Integer, ForeignKey("board_posts.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)
    created_at = Column(DateTime, default=now_kst)


# ─────────────────────────────
# 포스트 통계 모델
# ─────────────────────────────
class PostStats(Base):
    """Per-post counters, one row per post.

    Attributes:
        post_id: The post these stats belong to (unique).
        views: Total page views.
        likes: Cached like count.
        read_time: Accumulated reading time in seconds.
        unique_visitors: Number of distinct visitors.
        last_viewed_at: Time of the most recent view.
    """

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
        """Return a debug representation with post id and view count."""
        return f"<PostStats post_id={self.post_id} views={self.views}>"


# ─────────────────────────────
# 포스트 북마크 모델
# ─────────────────────────────
class PostBookmark(Base):
    """A user's bookmark of a post; unique per (user, post)."""

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
    """A user's like of a post; unique per (user, post)."""

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
    """A user following a category; unique per (user, category)."""

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
    """A user following another user as an author; unique per pair.

    Attributes:
        user_id, user: The follower.
        author_user_id, author: The followed author.
    """

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
    """An email address on the newsletter list, confirmed by double opt-in.

    Attributes:
        email: Subscriber address (unique).
        status: ``"pending"``, ``"confirmed"`` or ``"unsubscribed"``.
        verify_token: Token sent in the confirmation mail, if pending.
        source: Where the subscription came from (for example ``"home"``).
        created_at, confirmed_at: When the row was created and confirmed.
    """

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
    """Registry entry for a file a user uploaded.

    A file is linked to a draft (``draft_id``) until the post is published,
    then to the post (``post_id``).

    Attributes:
        user_id, user: The uploader.
        post_id, post: The post the file belongs to, once published.
        draft_id: The draft the file belongs to before publishing.
        file_type: ``image``, ``document``, ``text``, ``code``, ``archive``,
            ``video``, ``audio`` or ``other``.
        original_name: File name as uploaded.
        stored_name: Generated name on disk.
        file_path: Absolute path on disk.
        url: Public URL the file is served from.
        size_bytes, mime_type: Size and MIME type.
    """

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
        """Return a debug representation with id, file type and original name."""
        return f"<UploadedFile id={self.id} type={self.file_type!r} name={self.original_name!r}>"


# ─────────────────────────────
# 임시 저장 (Draft) 모델
# ─────────────────────────────
class Draft(Base):
    """An autosaved, unpublished post draft identified by a UUID string.

    Attributes:
        id: UUID primary key.
        user_id, user: The draft's owner.
        title, content: Draft title and body.
        tags: Tags as a JSON string.
        category_id: Chosen category, if any.
        is_private: Chosen visibility.
    """

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


# ─────────────────────────────
# 댓글 모델 (평문 텍스트)
# ─────────────────────────────
class Comment(Base):
    """A plain-text comment on a post.

    Attributes:
        post_id, post: The commented post.
        user_id, user: The commenter.
        body: Comment text.
        is_hidden: Hidden by moderation; excluded from queries by default.
    """

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("board_posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False)  # 관리자 숨김
    created_at = Column(DateTime, default=now_kst)

    post = relationship("BoardPost", back_populates="comments")
    user = relationship("User")

    def __repr__(self) -> str:
        """Return a debug representation with id and post id."""
        return f"<Comment id={self.id} post_id={self.post_id}>"


# ─────────────────────────────
# 신고 (모더레이션)
# ─────────────────────────────
class Report(Base):
    """A user's moderation report against a post or a comment.

    Attributes:
        reporter_user_id, reporter: The reporting user.
        target_type: ``"post"`` or ``"comment"``.
        target_id: Id of the reported post or comment.
        reason: Optional free-text reason.
        resolved: Whether an admin has closed the report.
    """

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    reporter_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_type = Column(String(20), nullable=False)   # "post" | "comment"
    target_id = Column(Integer, nullable=False, index=True)
    reason = Column(String(500), nullable=True)
    resolved = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=now_kst)

    reporter = relationship("User")

    def __repr__(self) -> str:
        """Return a debug representation with id and target."""
        return f"<Report id={self.id} {self.target_type}:{self.target_id}>"


# ─────────────────────────────
# 알림 (팔로우 / 댓글)
# ─────────────────────────────
class Notification(Base):
    """An in-app notification for one user.

    Attributes:
        user_id: The recipient.
        actor_user_id, actor: The user who triggered it, if any.
        type: ``"follow"`` or ``"comment"``.
        post_id, comment_id: The related post and comment, if any.
        is_read: Whether the recipient has seen it.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)   # 받는 사람
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)          # 행동한 사람
    type = Column(String(20), nullable=False)        # "follow" | "comment"
    post_id = Column(Integer, ForeignKey("board_posts.id", ondelete="CASCADE"), nullable=True)
    comment_id = Column(Integer, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=now_kst)

    actor = relationship("User", foreign_keys=[actor_user_id])

    def __repr__(self) -> str:
        """Return a debug representation with id, recipient and type."""
        return f"<Notification id={self.id} to={self.user_id} {self.type}>"


# ─────────────────────────────
# 매거진 레이아웃 템플릿 (사용자가 만든 레이아웃 저장·재사용)
# ─────────────────────────────
class LayoutTemplate(Base):
    """A magazine layout a user saved for reuse.

    Attributes:
        user_id, user: The owner.
        name: Template name.
        content_blocks: The saved layout as block JSON.
    """

    __tablename__ = "layout_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    content_blocks = Column(Text, nullable=False)   # 저장된 레이아웃(JSON)
    created_at = Column(DateTime, default=now_kst)

    user = relationship("User")

    def __repr__(self) -> str:
        """Return a debug representation with id and name."""
        return f"<LayoutTemplate id={self.id} {self.name!r}>"
