"""매거진 시작 템플릿(내장 프리셋). content_blocks(v3) JSON을 만들어 준다.

실제 잡지/에디토리얼 레이아웃 관례(표지·목차·피처 오프너·2~3단 그리드·포토
에세이·풀블리드·인터뷰·모자이크 그리드)를 바탕으로 구성했다.
- 제목은 heading, 본문은 text, 사진 자리는 image(빈 src → 에디터에서 업로드
  드롭존, 썸네일에선 플레이스홀더) 블록을 쓴다.
- 좌표계는 1000×1400 세로 페이지, 바깥 여백 70.
"""
from __future__ import annotations

import json

CW, CH = 1000, 1400
M = 70                      # 바깥 여백
CONT = CW - M * 2           # 본문 폭 860


def _h(x, y, w, h, html):
    return {"type": "heading", "x": x, "y": y, "w": w, "h": h, "content": html}


def _t(x, y, w, h, html):
    return {"type": "text", "x": x, "y": y, "w": w, "h": h, "content": html}


def _img(x, y, w, h):
    return {"type": "image", "x": x, "y": y, "w": w, "h": h, "src": ""}


def _div(x, y, w):
    return {"type": "text", "x": x, "y": y, "w": w, "h": 18,
            "content": "<div style='height:3px;background-color:#b4542f;width:100%'></div>"}


def _kicker(x, y, w, text):
    return _t(x, y, w, 40, f"<p style='letter-spacing:4px;text-transform:uppercase;color:#b4542f;font-size:16px'>{text}</p>")


def _cap(x, y, w, text="사진 캡션"):
    return _t(x, y, w, 36, f"<p style='font-size:15px;color:#8a7c6d'>{text}</p>")


# ── 레이아웃들 ────────────────────────────────────────────

def _blank():
    return _page([])


def _cover():
    return _page([
        _img(0, 0, CW, 840),
        _h(M, 60, CONT, 60, "<h1 style='text-align:center;letter-spacing:10px;font-size:30px;color:#fff'>MAGAZINE</h1>"),
        _h(M, 900, CONT, 240, "<h1 style='font-size:84px;font-weight:800;line-height:1.05'>표지 제목을<br>입력하세요</h1>"),
        _t(M, 1165, CONT, 50, "<p style='font-size:24px;color:#4c4239'>부제 또는 한 줄 소개</p>"),
        _t(M, 1255, CONT, 40, "<p style='font-size:18px;color:#8a7c6d'>Issue 01 · by 작성자</p>"),
    ])


def _contents():
    return _page([
        _h(M, 90, 520, 90, "<h1 style='font-size:60px;font-weight:800'>Contents</h1>"),
        _div(M, 205, 520),
        _t(M, 250, 520, 64, "<p style='font-size:22px'><b style='color:#b4542f'>01</b>&nbsp;&nbsp;첫 번째 글 제목</p>"),
        _t(M, 334, 520, 64, "<p style='font-size:22px'><b style='color:#b4542f'>02</b>&nbsp;&nbsp;두 번째 글 제목</p>"),
        _t(M, 418, 520, 64, "<p style='font-size:22px'><b style='color:#b4542f'>03</b>&nbsp;&nbsp;세 번째 글 제목</p>"),
        _t(M, 502, 520, 64, "<p style='font-size:22px'><b style='color:#b4542f'>04</b>&nbsp;&nbsp;네 번째 글 제목</p>"),
        _t(M, 586, 520, 64, "<p style='font-size:22px'><b style='color:#b4542f'>05</b>&nbsp;&nbsp;다섯 번째 글 제목</p>"),
        _img(640, 250, 290, 470),
        _cap(640, 730, 290, "이번 호 하이라이트"),
    ])


def _feature():
    return _page([
        _kicker(M, 90, CONT, "FEATURE"),
        _h(M, 140, CONT, 230, "<h1 style='font-size:72px;font-weight:800;line-height:1.08'>큰 헤드라인을<br>여기에</h1>"),
        _t(M, 390, CONT, 110, "<p style='font-size:26px;color:#4c4239;line-height:1.5'>스탠드퍼스트 — 기사의 핵심을 한두 문장으로 요약하세요.</p>"),
        _t(M, 510, 400, 40, "<p style='font-size:16px;color:#8a7c6d'>글 · 작성자</p>"),
        _img(M, 570, CONT, 760),
    ])


def _two_col():
    return _page([
        _h(M, 90, CONT, 130, "<h1 style='font-size:58px;font-weight:800'>기사 제목</h1>"),
        _t(M, 235, CONT, 80, "<p style='font-size:22px;color:#4c4239'>리드 문장 — 기사의 방향을 한 문장으로.</p>"),
        _div(M, 335, CONT),
        _t(M, 380, 410, 500, "<p style='font-size:18px;line-height:1.8'>왼쪽 단 본문을 입력하세요.</p>"),
        _t(520, 380, 410, 500, "<p style='font-size:18px;line-height:1.8'>오른쪽 단 본문을 입력하세요.</p>"),
        _t(M, 910, CONT, 170, "<blockquote style='border-left:4px solid #b4542f;padding-left:18px;margin:0;font-size:30px;font-style:italic;color:#4c4239'>인상적인 한 문장을 인용구로.</blockquote>"),
        _t(M, 1110, CONT, 210, "<p style='font-size:18px;line-height:1.8'>마무리 본문.</p>"),
    ])


def _three_col():
    gap = 30
    w = (CONT - gap * 2) // 3  # 266
    x1, x2, x3 = M, M + w + gap, M + (w + gap) * 2
    return _page([
        _h(M, 90, CONT, 120, "<h1 style='font-size:52px;font-weight:800'>기사 제목</h1>"),
        _t(M, 215, CONT, 60, "<p style='font-size:20px;color:#4c4239'>리드 문장.</p>"),
        _div(M, 290, CONT),
        _t(x1, 330, w, 990, "<p style='font-size:17px;line-height:1.8'>첫째 단 본문.</p>"),
        _t(x2, 330, w, 990, "<p style='font-size:17px;line-height:1.8'>둘째 단 본문.</p>"),
        _t(x3, 330, w, 990, "<p style='font-size:17px;line-height:1.8'>셋째 단 본문.</p>"),
    ])


def _photo():
    return _page([
        _h(M, 90, CONT, 90, "<h1 style='font-size:50px;font-weight:800'>포토 에세이</h1>"),
        _img(M, 215, CONT, 520),
        _cap(M, 750, CONT),
        _img(M, 820, 415, 400),
        _img(515, 820, 415, 400),
        _cap(M, 1240, CONT),
    ])


def _full_bleed():
    return _page([
        _img(0, 0, CW, CH),
        _h(70, 1040, 760, 200, "<h1 style='font-size:76px;font-weight:800;line-height:1.08;color:#fff'>사진 위에<br>제목</h1>"),
        _t(70, 1285, CONT, 40, "<p style='font-size:16px;color:#fff'>캡션 또는 사진 크레딧</p>"),
    ])


def _interview():
    return _page([
        _kicker(M, 90, CONT, "INTERVIEW"),
        _h(M, 140, CONT, 120, "<h1 style='font-size:56px;font-weight:800'>인터뷰 제목</h1>"),
        _img(M, 300, 360, 360),
        _t(470, 300, 460, 360, "<p style='font-size:22px;line-height:1.6;color:#4c4239'>인터뷰 대상 소개 문단을 입력하세요.</p>"),
        _t(M, 710, CONT, 70, "<p style='font-size:21px'><b style='color:#b4542f'>Q.</b> 질문을 입력하세요?</p>"),
        _t(M, 790, CONT, 150, "<p style='font-size:18px;line-height:1.8'>답변 내용.</p>"),
        _t(M, 960, CONT, 70, "<p style='font-size:21px'><b style='color:#b4542f'>Q.</b> 다음 질문은?</p>"),
        _t(M, 1040, CONT, 280, "<p style='font-size:18px;line-height:1.8'>답변 내용.</p>"),
    ])


def _gallery():
    return _page([
        _h(M, 90, CONT, 80, "<h1 style='font-size:48px;font-weight:800'>갤러리</h1>"),
        _img(70, 200, 560, 360),
        _img(650, 200, 280, 360),
        _img(70, 580, 280, 280),
        _img(363, 580, 267, 280),
        _img(650, 580, 280, 280),
        _img(70, 880, 860, 360),
        _cap(70, 1255, CONT, "캡션 — 사진 설명"),
    ])


def _page(blocks):
    return {"cw": CW, "ch": CH, "blocks": blocks}


_PRESETS = [
    {"key": "blank", "name": "빈 레이아웃", "description": "백지에서 자유롭게", "icon": "bi-file-earmark", "build": _blank},
    {"key": "cover", "name": "표지", "description": "큰 사진 + 마스트헤드 + 제목", "icon": "bi-file-earmark-richtext", "build": _cover},
    {"key": "contents", "name": "목차", "description": "Contents + 글 목록 + 하이라이트", "icon": "bi-list-ol", "build": _contents},
    {"key": "feature", "name": "피처 오프너", "description": "헤드라인 + 리드 + 큰 사진", "icon": "bi-newspaper", "build": _feature},
    {"key": "two-col", "name": "2단 기사", "description": "2단 본문 + 인용구", "icon": "bi-layout-split", "build": _two_col},
    {"key": "three-col", "name": "3단 기사", "description": "클래식 3단 편집", "icon": "bi-layout-three-columns", "build": _three_col},
    {"key": "photo", "name": "포토 에세이", "description": "큰 사진 + 2장 + 캡션", "icon": "bi-images", "build": _photo},
    {"key": "full-bleed", "name": "풀블리드 사진", "description": "페이지 꽉 찬 사진 + 제목", "icon": "bi-image", "build": _full_bleed},
    {"key": "interview", "name": "인터뷰 Q&A", "description": "인물 사진 + 질문/답변", "icon": "bi-chat-quote", "build": _interview},
    {"key": "gallery", "name": "그리드 갤러리", "description": "모자이크 사진 그리드", "icon": "bi-grid-3x3-gap", "build": _gallery},
]


def list_starters():
    return [{"key": p["key"], "name": p["name"], "description": p["description"], "icon": p["icon"]} for p in _PRESETS]


def get_starter_blocks(key: str):
    for p in _PRESETS:
        if p["key"] == key:
            return json.dumps({"v": 3, "pages": [p["build"]()]}, ensure_ascii=False)
    return None
