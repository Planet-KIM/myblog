"""매거진 시작 템플릿(내장 프리셋). content_blocks(v3) JSON을 만들어 준다.

블록은 모두 '텍스트' 타입(placeholder)이라 항상 렌더되고, 에디터에서 자유롭게
바꿀 수 있다. 이미지 자리는 안내 박스로 표시한다.
"""
from __future__ import annotations

import json

CW, CH = 1000, 1400


def _t(x, y, w, h, html):
    return {"type": "text", "x": x, "y": y, "w": w, "h": h, "content": html}


def _page(blocks):
    return {"cw": CW, "ch": CH, "blocks": blocks}


def _cover():
    return _page([
        _t(100, 180, 800, 50, "<p style='font-size:22px;letter-spacing:4px;text-transform:uppercase;text-align:center;color:#8a7c6d'>MAGAZINE</p>"),
        _t(70, 520, 860, 260, "<p style='font-size:88px;font-weight:800;text-align:center;line-height:1.08'>제목을<br>입력하세요</p>"),
        _t(150, 830, 700, 80, "<p style='font-size:28px;text-align:center;color:#4c4239'>부제 또는 한 줄 소개</p>"),
        _t(300, 1250, 400, 40, "<p style='font-size:20px;text-align:center;color:#8a7c6d'>by 작성자</p>"),
    ])


def _feature():
    return _page([
        _t(80, 120, 840, 150, "<p style='font-size:56px;font-weight:800;line-height:1.1'>기사 제목</p>"),
        _t(80, 300, 840, 120, "<p style='font-size:26px;color:#4c4239;line-height:1.5'>리드 문장 — 이 기사의 핵심을 한두 문장으로 요약하세요.</p>"),
        _t(80, 470, 400, 820, "<p style='font-size:19px;line-height:1.8'>왼쪽 단 본문을 입력하세요.</p>"),
        _t(520, 470, 400, 820, "<p style='font-size:19px;line-height:1.8'>오른쪽 단 본문을 입력하세요.</p>"),
    ])


def _photo():
    box = "<div style='height:100%;display:flex;align-items:center;justify-content:center;background:#efe7d9;color:#8a7c6d;font-size:22px;border-radius:12px'>📷 이미지</div>"
    return _page([
        _t(80, 120, 840, 100, "<p style='font-size:48px;font-weight:800'>포토 에세이</p>"),
        _t(80, 270, 840, 470, box),
        _t(80, 760, 840, 40, "<p style='font-size:18px;color:#8a7c6d'>사진 캡션</p>"),
        _t(80, 840, 400, 380, box),
        _t(520, 840, 400, 380, box),
    ])


_PRESETS = [
    {"key": "cover", "name": "표지", "description": "큰 제목 + 부제 + 작성자", "icon": "bi-file-earmark-richtext", "build": _cover},
    {"key": "feature", "name": "피처 스프레드", "description": "제목 + 리드 + 2단 본문", "icon": "bi-layout-text-window-reverse", "build": _feature},
    {"key": "photo", "name": "포토 에세이", "description": "제목 + 사진 + 캡션", "icon": "bi-images", "build": _photo},
]


def list_starters():
    out = []
    for p in _PRESETS:
        out.append({"key": p["key"], "name": p["name"], "description": p["description"], "icon": p["icon"]})
    return out


def get_starter_blocks(key: str):
    for p in _PRESETS:
        if p["key"] == key:
            return json.dumps({"v": 3, "pages": [p["build"]()]}, ensure_ascii=False)
    return None
