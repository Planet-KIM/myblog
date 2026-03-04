from typing import Optional
from datetime import datetime, timedelta
import markdown
import copy

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from app import models
from app.database import get_db
from app.auth_utils import get_current_user_optional
from app.cv_content import (
    cv_profile,
    education,
    experience,
    industry,
    skills,
    projects,
    skill_palette,
    research_interest,
)

router = APIRouter(prefix="/blog", tags=["blog"])

def render_markdown_fields(cv):
    """
    cv_content 에서 넘어온 데이터 구조에 맞춰
    **bold** 같은 인라인 마크다운을 HTML(<strong> 등)로 변환한다.
    - experience.ko.bullets / experience.en.bullets
    - projects[*].bullets_ko / projects[*].bullets_en
    만 처리한다.
    """
    cv_copy = copy.deepcopy(cv)

    def md_list(lst):
        """문자열 리스트에 markdown 변환 적용"""
        return [markdown.markdown(text, extensions=["extra"]) for text in lst]

    # 1) 연구실 Experience bullets (ko/en)
    exp = cv_copy.get("experience")
    if isinstance(exp, dict):
        for lang in ("ko", "en"):
            section = exp.get(lang)
            if isinstance(section, dict) and isinstance(section.get("bullets"), list):
                section["bullets"] = md_list(section["bullets"])

    # 2) Projects bullets_ko / bullets_en
    proj_list = cv_copy.get("projects") or []
    if isinstance(proj_list, list):
        for proj in proj_list:
            if not isinstance(proj, dict):
                continue
            for key in ("bullets_ko", "bullets_en"):
                if isinstance(proj.get(key), list):
                    proj[key] = md_list(proj[key])

    # 3) Research Interest 처리
    ri = cv_copy.get("research_interest")
    if isinstance(ri, dict):
        for sec in ri.get("sections", []):
            if isinstance(sec.get("bullets"), list):
                sec["bullets"] = md_list(sec["bullets"])
    return cv_copy

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["blog"])


@router.get("/", response_class=HTMLResponse)
def read_index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """홈(/) 페이지: 비로그인=public, 로그인=public+내 private"""
    q = db.query(models.BoardPost)

    if current_user:
        posts = (
            q.filter(
                or_(
                    models.BoardPost.is_private == False,
                    models.BoardPost.user_id == current_user.id,
                )
            )
            .order_by(models.BoardPost.created_at.desc())
            .all()
        )
    else:
        posts = (
            q.filter(models.BoardPost.is_private == False)
            .order_by(models.BoardPost.created_at.desc())
            .all()
        )

    board_posts = posts[:5]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "posts": posts,
            "board_posts": board_posts,
            "current_user": current_user,
        },
    )


@router.get("/main", response_class=HTMLResponse)
def main_page(
    request: Request,
    db: Session = Depends(get_db),
    published: bool = False,
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """
    CV 메인(/main)

    Recent Posts:
      - 작성 후 1일 이내(posted within last 24h)만 조회
      - 비로그인: public만
      - 로그인: public + 내가 쓴 private
    """
    q = db.query(models.BoardPost)
    cutoff = datetime.utcnow() - timedelta(days=1)

    if current_user:
        recent_posts = (
            q.filter(
                models.BoardPost.created_at >= cutoff,
                or_(
                    models.BoardPost.is_private == False,
                    models.BoardPost.user_id == current_user.id,
                ),
            )
            .order_by(models.BoardPost.created_at.desc())
            .limit(5)
            .all()
        )
    else:
        recent_posts = (
            q.filter(
                models.BoardPost.is_private == False,
                models.BoardPost.created_at >= cutoff,
            )
            .order_by(models.BoardPost.created_at.desc())
            .limit(5)
            .all()
        )

    # 프로젝트는 end_year(없으면 현재=9999), start_year 기준으로 내림차순 정렬
    sorted_projects = sorted(
        projects,
        key=lambda p: (
            p.get("end_year") or 9999,
            p.get("start_year") or 0,
        ),
        reverse=True,
    )

    cv = {
        "profile": cv_profile,
        "education": education,
        "experience": experience,
        "industry": industry,
        "skills": skills,
        "skill_palette": skill_palette,
        "projects": sorted_projects,
        "research_interest": research_interest,
    }
    # 추가항
    cv = render_markdown_fields(cv)
    return templates.TemplateResponse(
        "main.html",
        {
            "request": request,
            "published": published,
            "recent_posts": recent_posts,
            "current_user": current_user,
            "cv": cv,
            "current_year": datetime.utcnow().year,
        },
    )


@router.get("/posts/new")
def legacy_posts_new_redirect():
    return RedirectResponse("/board/new", status_code=307)


@router.get("/posts/{post_id}", response_class=HTMLResponse)
def read_post(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    post = db.query(models.BoardPost).filter(models.BoardPost.id == post_id).first()
    if not post:
        return RedirectResponse("/", status_code=302)

    if post.is_private:
        if not current_user or post.user_id != current_user.id:
            return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        "post_detail.html",
        {
            "request": request,
            "post": post,
            "current_user": current_user,
        },
    )
