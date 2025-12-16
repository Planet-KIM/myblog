from typing import Optional
import re

from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from . import models

# bcrypt 72바이트 제한 문제 피하기 위해 pbkdf2_sha256 사용
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)

# 비밀번호 규칙: 8자 이상, 영문 + 숫자 + 특수문자 각각 1개 이상
PASSWORD_REGEX = re.compile(
    r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*()_+\-={}\[\]:;\"'`<>,.?/]).{8,}$"
)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_rule(password: str) -> None:
    """
    비밀번호가 규칙을 만족하지 않으면 HTTPException을 발생시킨다.
    """
    if not PASSWORD_REGEX.match(password):
        raise HTTPException(
            status_code=400,
            detail="비밀번호는 8자 이상이며, 영문/숫자/특수문자를 각각 1개 이상 포함해야 합니다.",
        )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> models.User:
    """
    세션에 저장된 user_id로 현재 로그인한 사용자 조회.
    없으면 403.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="로그인이 필요합니다.")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=403, detail="사용자를 찾을 수 없습니다.")
    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """
    로그인 안 되어 있으면 None, 되어 있으면 User 반환.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return user

