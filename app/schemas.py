from datetime import datetime
from pydantic import BaseModel


class PostBase(BaseModel):
    title: str
    content: str
    author: str = "anonymous"


class PostCreate(PostBase):
    pass


class Post(PostBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BoardPostBase(BaseModel):
    title: str
    content: str
    author: str = "anonymous"


class BoardPostCreate(BoardPostBase):
    is_private: bool = False


class BoardPost(BaseModel):
    id: int
    title: str
    content: str
    author: str
    is_private: bool
    created_at: datetime

    class Config:
        from_attributes = True
