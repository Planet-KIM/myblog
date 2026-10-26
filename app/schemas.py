"""Pydantic schemas for posts and board posts.

These are legacy schemas; no module in the app currently imports them.
"""
from datetime import datetime
from pydantic import BaseModel


class PostBase(BaseModel):
    """Fields shared by every post schema: title, content and author name."""

    title: str
    content: str
    author: str = "anonymous"


class PostCreate(PostBase):
    """Input for creating a post; same fields as ``PostBase``."""

    pass


class Post(PostBase):
    """A stored post as returned to clients, with id and timestamps."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        """Allow building the schema from ORM objects (``from_attributes``)."""

        from_attributes = True


class BoardPostBase(BaseModel):
    """Fields shared by board post schemas: title, content and author name."""

    title: str
    content: str
    author: str = "anonymous"


class BoardPostCreate(BoardPostBase):
    """Input for creating a board post, with an optional private flag."""

    is_private: bool = False


class BoardPost(BaseModel):
    """A stored board post as returned to clients."""

    id: int
    title: str
    content: str
    author: str
    is_private: bool
    created_at: datetime

    class Config:
        """Allow building the schema from ORM objects (``from_attributes``)."""

        from_attributes = True
