"""여행 일정 타임라인 파서.

입력 예시(한 블록):
    DAY 1
    왕궁 & 에메랄드 사원:09:00
    왓 포:11:00
    ...
    DAY 2
    ...

규칙:
  - '# 제목' (맨 앞 #) → 날짜/구간 헤더. 언어·표현 자유 (예: '# 첫째 날', '# Jour 1')
  - 'DAY n' / 'n일차' / 'n일째' → 헤더 (하위호환 자동 인식)
  - '라벨:HH:MM' (전각 콜론 ：도 허용) → 시간 있는 일정
  - 그 외 줄 → 시간 없는 일정(라벨만)
  - 빈 줄 무시
반환: [{"title": "첫째 날", "events": [{"label": ..., "time": "09:00"}, ...]}, ...]
"""
from __future__ import annotations

import re

_TIME = re.compile(r"^(.*?)[:：]\s*(\d{1,2}:\d{2})\s*$")
_DAY = re.compile(r"(?i)^(day\b.*|\d+\s*일\s*차.*|\d+\s*일째.*)$")


def parse_timeline(text: str) -> list[dict]:
    days: list[dict] = []
    cur: dict | None = None

    def ensure_day():
        nonlocal cur
        if cur is None:
            cur = {"title": "", "events": []}
            days.append(cur)

    def new_day(title):
        nonlocal cur
        cur = {"title": title, "events": []}
        days.append(cur)

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _TIME.match(line)
        if m:
            ensure_day()
            cur["events"].append({"label": m.group(1).strip(), "time": m.group(2).strip()})
        elif line.startswith("#"):              # 언어 무관 헤더 표시
            new_day(line.lstrip("#").strip())
        elif _DAY.match(line):                  # DAY n / n일차 (하위호환)
            new_day(line)
        else:
            ensure_day()
            cur["events"].append({"label": line, "time": ""})

    return [d for d in days if d["events"] or d["title"].strip()]


def is_timeline_like(text: str) -> bool:
    """텍스트가 타임라인 형식으로 보이면 True(이벤트 2개 이상)."""
    days = parse_timeline(text)
    return sum(len(d["events"]) for d in days) >= 2
