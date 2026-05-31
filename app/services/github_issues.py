from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _format_github_time(value: str) -> str:
    """
    GitHub ISO8601 시각을 사람이 읽기 쉬운 문자열로 변환.
    변환 실패 시 원문을 그대로 반환한다.
    """
    if not value:
        return value
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _extract_error_message(body: str) -> str:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body.strip() or "알 수 없는 오류"
    if isinstance(parsed, dict):
        message = parsed.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return body.strip() or "알 수 없는 오류"


def _to_body_preview(text: str, max_len: int = 220) -> str:
    """
    GitHub markdown body를 카드 미리보기용 평문으로 압축.
    """
    if not text:
        return ""

    preview = text
    # fenced code block 제거
    preview = re.sub(r"```[\s\S]*?```", " ", preview)
    # inline code
    preview = re.sub(r"`([^`]+)`", r"\1", preview)
    # markdown link -> label
    preview = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", preview)
    # heading / quote / list prefix 정리
    preview = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", preview)
    preview = re.sub(r"(?m)^\s*>\s*", "", preview)
    preview = re.sub(r"(?m)^\s*[-*+]\s+", "", preview)
    preview = re.sub(r"(?m)^\s*\d+\.\s+", "", preview)
    # 굵게/이탤릭 기호 제거
    preview = preview.replace("**", "").replace("__", "")
    preview = preview.replace("*", "").replace("_", "")

    preview = re.sub(r"\s+", " ", preview).strip()
    if len(preview) > max_len:
        preview = preview[:max_len].rsplit(" ", 1)[0] + "..."
    return preview


def fetch_github_issues(
    repo: str,
    state: str = "open",
    page: int = 1,
    per_page: int = 20,
    token: str = "",
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    """
    GitHub Issues API를 호출해 이슈 목록을 반환한다.

    반환 스키마:
      {
        "items": [...],
        "has_next": bool,
        "has_prev": bool,
        "error": Optional[str],
        "rate_remaining": Optional[str],
      }
    """
    state_mode = (state or "open").strip().lower()
    if state_mode not in {"open", "closed", "all"}:
        state_mode = "open"

    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 20), 100))

    repo_name = (repo or "").strip()
    if "/" not in repo_name:
        return {
            "items": [],
            "has_next": False,
            "has_prev": page > 1,
            "error": "GITHUB_REPO 설정이 올바르지 않습니다. (owner/repo 형식)",
            "rate_remaining": None,
        }

    query = urlencode(
        {
            "state": state_mode,
            "sort": "updated",
            "direction": "desc",
            "page": page,
            "per_page": per_page,
        }
    )
    url = f"https://api.github.com/repos/{repo_name}/issues?{query}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "myblog-issues-dashboard",
    }
    token_value = (token or "").strip()
    if token_value:
        headers["Authorization"] = f"Bearer {token_value}"

    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            payload = json.loads(body)
            if not isinstance(payload, list):
                return {
                    "items": [],
                    "has_next": False,
                    "has_prev": page > 1,
                    "error": "GitHub 응답 형식이 예상과 다릅니다.",
                    "rate_remaining": resp.headers.get("X-RateLimit-Remaining"),
                }

            # /issues endpoint는 PR도 포함하므로 제거
            issues = [item for item in payload if isinstance(item, dict) and "pull_request" not in item]

            items: list[dict[str, Any]] = []
            for item in issues:
                labels = item.get("labels") if isinstance(item.get("labels"), list) else []
                items.append(
                    {
                        "number": item.get("number"),
                        "title": item.get("title") or "(no title)",
                        "state": item.get("state") or "open",
                        "url": item.get("html_url") or "",
                        "body_preview": _to_body_preview(item.get("body") or ""),
                        "author": (item.get("user") or {}).get("login", "unknown"),
                        "comments": item.get("comments") or 0,
                        "created_at": _format_github_time(item.get("created_at") or ""),
                        "updated_at": _format_github_time(item.get("updated_at") or ""),
                        "labels": [lbl.get("name", "") for lbl in labels if isinstance(lbl, dict)],
                    }
                )

            link_header = resp.headers.get("Link", "")
            has_next = 'rel="next"' in link_header
            return {
                "items": items,
                "has_next": has_next,
                "has_prev": page > 1,
                "error": None,
                "rate_remaining": resp.headers.get("X-RateLimit-Remaining"),
            }

    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        message = _extract_error_message(raw)
        return {
            "items": [],
            "has_next": False,
            "has_prev": page > 1,
            "error": f"GitHub API 오류 ({exc.code}): {message}",
            "rate_remaining": exc.headers.get("X-RateLimit-Remaining") if exc.headers else None,
        }
    except URLError as exc:
        return {
            "items": [],
            "has_next": False,
            "has_prev": page > 1,
            "error": f"GitHub API 연결 실패: {exc.reason}",
            "rate_remaining": None,
        }
    except Exception as exc:  # 방어적 fallback
        return {
            "items": [],
            "has_next": False,
            "has_prev": page > 1,
            "error": f"GitHub 이슈 조회 중 예외 발생: {exc}",
            "rate_remaining": None,
        }
