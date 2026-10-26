"""
글별 동적 OG 이미지 생성 (1200×630 PNG)
========================================
글 제목·작성자를 브랜드 카드로 그려, 본문에 대표 이미지가 없는 글도
SNS 공유 시 밋밋한 기본 썸네일 대신 '매거진 표지' 같은 미리보기를 갖게 한다.

- 폰트: 저장소에 번들된 Pretendard(OFL, 한글 포함). 없으면 PIL 기본 폰트로 폴백.
- 색: theme.css 브랜드 토큰(테라코타/스카이/세이지 + 웜 페이퍼)과 일치.
- 순수 Pillow만 사용(헤드리스 서버 안전). 네트워크/브라우저 불필요.
"""
from __future__ import annotations

import html as _html
import json as _json
import logging
import re as _re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# ── 캔버스 ────────────────────────────────────────────────
W, H = 1200, 630
PAD = 84  # 좌우 안전 여백

# ── 브랜드 색 (theme.css 와 동일) ──────────────────────────
PAPER = (248, 244, 238)   # #f8f4ee  웜 페이퍼
PAPER_HI = (253, 249, 243) # 살짝 밝은 상단
INK = (42, 35, 32)        # #2a2320  본문 잉크
MUTED = (138, 124, 109)   # #8a7c6d  보조 텍스트
TERRA = (180, 84, 47)     # #b4542f  테라코타(주색)
SKY = (42, 130, 196)      # #2a82c4  스카이(강조)
SAGE = (63, 143, 92)      # #3f8f5c  세이지(보조)
CREAM = (253, 248, 242)   # 마크 안쪽 글자

_FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_FONT_BOLD = _FONT_DIR / "Pretendard-Bold.ttf"


@lru_cache(maxsize=32)
def _font(size: int) -> ImageFont.FreeTypeFont:
    """Pretendard-Bold 를 크기별 캐시. 폰트 파일이 없으면 기본 폰트."""
    try:
        return ImageFont.truetype(str(_FONT_BOLD), size)
    except Exception:  # noqa: BLE001 — 폰트 누락 시에도 500 금지
        logger.warning("Pretendard 폰트를 찾지 못해 기본 폰트로 OG 이미지를 그립니다.")
        return ImageFont.load_default()


@lru_cache(maxsize=1)
def _supported() -> Optional[frozenset]:
    """번들 폰트가 지원하는 코드포인트 집합(없으면 None → 필터 생략)."""
    try:
        from fontTools.ttLib import TTFont

        cmap = TTFont(str(_FONT_BOLD)).getBestCmap()
        return frozenset(cmap.keys())
    except Exception:  # noqa: BLE001
        return None


def _clean(text: str) -> str:
    """폰트에 없는 글자(이모지·변형선택자 등)를 제거해 두부(□)·줄무늬 상자를 방지."""
    if not text:
        return ""
    text = " ".join(text.split())  # 개행/연속 공백 정리
    cps = _supported()
    if cps is None:
        return text
    out = "".join(ch for ch in text if ch == " " or ord(ch) in cps)
    return " ".join(out.split()).strip()


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    """Return the rendered width of ``text`` in pixels when drawn with ``font``."""
    return draw.textlength(text, font=font)


def _wrap(draw, text: str, font, max_w: float, max_lines: int) -> list[str]:
    """
    공백 우선 그리디 줄바꿈. 한 단어(긴 한글 연속)가 폭을 넘으면 글자 단위로 쪼갠다.
    max_lines 를 넘으면 마지막 줄 끝을 … 로 처리.
    """
    words = text.split(" ")
    lines: list[str] = []
    cur = ""

    def push(line: str):
        """Commit ``line`` as the next finished output line."""
        lines.append(line)

    for word in words:
        candidate = word if not cur else cur + " " + word
        if _text_w(draw, candidate, font) <= max_w:
            cur = candidate
            continue
        # 현재 줄을 확정하고 새 단어 시작 (단어 자체가 너무 길면 글자 단위 분할)
        if cur:
            push(cur)
            cur = ""
            if len(lines) >= max_lines:
                break
        if _text_w(draw, word, font) <= max_w:
            cur = word
        else:
            piece = ""
            for ch in word:
                if _text_w(draw, piece + ch, font) <= max_w:
                    piece += ch
                else:
                    push(piece)
                    piece = ch
                    if len(lines) >= max_lines:
                        break
            cur = piece
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        push(cur)

    # 잘렸으면 말줄임
    if len(lines) >= max_lines:
        last = lines[max_lines - 1]
        if _text_w(draw, text, font) > _text_w(draw, " ".join(lines[:max_lines]), font):
            while last and _text_w(draw, last + "…", font) > max_w:
                last = last[:-1]
            lines[max_lines - 1] = (last + "…") if last else "…"
    return lines[:max_lines]


def _fit_title(draw, title: str, max_w: float, max_lines: int = 3):
    """제목이 max_lines 안에 들어오는 가장 큰 폰트 크기를 찾는다."""
    for size in range(84, 45, -4):
        font = _font(size)
        lines = _wrap(draw, title, font, max_w, max_lines + 1)
        if len(lines) <= max_lines:
            return font, _wrap(draw, title, font, max_w, max_lines), size
    font = _font(46)
    return font, _wrap(draw, title, font, max_w, max_lines), 46


def _vgradient(top: tuple, bottom: tuple) -> Image.Image:
    """위→아래 수직 그라데이션 배경(웜 페이퍼의 은은한 깊이)."""
    base = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / (H - 1)
        base.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return base.resize((W, H))


def _planet_mark(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int):
    """브랜드 행성(원 + 기울어진 고리) 마크."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=TERRA)
    # 고리: 얇은 타원 외곽선
    rw, rh = int(r * 1.7), int(r * 0.6)
    for off in range(0, 5):  # 두께
        draw.ellipse(
            [cx - rw, cy - rh + off - 2, cx + rw, cy + rh + off - 2],
            outline=TERRA, width=2,
        )


def _initial_avatar(draw, cx, cy, r, letter: str, color):
    """Draw a filled circle with ``letter`` centred in it in cream, like an avatar.

    Args:
        draw: Drawing context of the target image.
        cx: Circle centre x in pixels.
        cy: Circle centre y in pixels.
        r: Circle radius in pixels; the letter is sized at ``1.1 * r``.
        letter: The character to show, usually the author's initial.
        color: RGB fill colour of the circle.
    """
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    f = _font(int(r * 1.1))
    bbox = draw.textbbox((0, 0), letter, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), letter, font=f, fill=CREAM)


def render_post_og(
    title: str,
    author_name: str = "",
    *,
    handle: str = "",
    tag: str = "",
    site: str = "Planet KIM",
) -> bytes:
    """글 제목·작성자로 브랜드 OG 카드(PNG 바이트)를 만든다."""
    title = _clean(title) or "제목 없는 글"
    author_name = _clean(author_name)
    handle = _clean(handle)
    tag = _clean(tag)
    site = _clean(site) or "Planet KIM"

    img = _vgradient(PAPER_HI, PAPER)
    draw = ImageDraw.Draw(img)

    # 좌측 브랜드 액센트 바 + 하단 브랜드 3색 점
    draw.rectangle([0, 0, 12, H], fill=TERRA)

    # ── 헤더: 행성 마크 + 워드마크 ─────────────────────────
    hx, hy = PAD, 74
    _planet_mark(draw, hx + 16, hy + 2, 18)
    wf = _font(30)
    draw.text((hx + 52, hy - 16), site, font=wf, fill=TERRA)
    # 상단 우측: 글 종류 라벨
    label = (tag or "글").strip()
    lf = _font(24)
    lw = _text_w(draw, label, lf)
    chip_pad = 18
    draw.rounded_rectangle(
        [W - PAD - lw - chip_pad * 2, hy - 18, W - PAD, hy + 24],
        radius=21, fill=(237, 229, 220),
    )
    draw.text((W - PAD - lw - chip_pad, hy - 12), label, font=lf, fill=TERRA)

    # 헤더 구분선
    draw.line([(PAD, hy + 52), (W - PAD, hy + 52)], fill=(226, 216, 205), width=2)

    # ── 제목 (자동 맞춤, 중앙 영역) ────────────────────────
    max_w = W - PAD * 2
    font, lines, size = _fit_title(draw, title, max_w, max_lines=3)
    line_h = int(size * 1.22)
    block_h = line_h * len(lines)
    ty = int((H - block_h) / 2) + 18
    for ln in lines:
        draw.text((PAD, ty), ln, font=font, fill=INK)
        ty += line_h

    # ── 푸터: 작성자 ──────────────────────────────────────
    fy = H - 92
    draw.line([(PAD, fy - 20), (W - PAD, fy - 20)], fill=(226, 216, 205), width=2)
    if author_name:
        ar = 28
        acx, acy = PAD + ar, fy + ar
        initial = next((c for c in author_name if c.isalnum()), author_name[:1] or "·").upper()
        _initial_avatar(draw, acx, acy, ar, initial, TERRA)
        nf = _font(32)
        # @handle 줄을 따로 보일 때만 이름을 위로 올려 2줄 배치
        show_handle = bool(handle) and handle.lower() != author_name.lstrip("@").lower()
        if show_handle:
            draw.text((acx + ar + 20, fy + 4), author_name, font=nf, fill=INK)
            draw.text((acx + ar + 20, fy + 44), "@" + handle, font=_font(24), fill=MUTED)
        else:
            draw.text((acx + ar + 20, fy + 18), author_name, font=nf, fill=INK)
    # 우측 하단 브랜드 3색 점
    dots_y = fy + 30
    for i, c in enumerate((TERRA, SKY, SAGE)):
        dx = W - PAD - 10 - i * 34
        draw.ellipse([dx - 11, dots_y - 11, dx + 11, dots_y + 11], fill=c)

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _timeline_h_png(days: list, width: int) -> bytes:
    """가로 타임라인 — 폭을 넘으면 다음 줄로 자동 줄바꿈."""
    import io

    PAD = 24
    item_w = 116
    time_h = 26
    mark_h = 20
    label_lh = 22
    row_gap = 14
    title_h = 56
    top = 24
    W = int(width)
    usable = max(item_w, W - PAD * 2)
    per_row = max(1, usable // item_w)
    f_day, f_time, f_label = _font(28), _font(19), _font(20)

    tmp = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    plan = []
    H = top
    for d in days:
        evs = d["events"]
        rows = [evs[i:i + per_row] for i in range(0, len(evs), per_row)] or [[]]
        wrapped = {i: _wrap(tmp, _clean(ev.get("label") or ""), f_label, item_w - 12, 2) for i, ev in enumerate(evs)}
        max_lines = max((len(v) for v in wrapped.values()), default=1)
        row_h = time_h + mark_h + max_lines * label_lh + row_gap
        plan.append((d, rows, evs, wrapped, row_h))
        H += (title_h if _clean(d.get("title") or "") else 10) + len(rows) * row_h
    H = max(H + 16, 140)

    img = _vgradient(PAPER_HI, PAPER).resize((W, H))
    draw = ImageDraw.Draw(img)
    y = top
    for d, rows, evs, wrapped, row_h in plan:
        title = _clean(d.get("title") or "")
        if title:
            draw.text((PAD, y + 6), title, font=f_day, fill=TERRA)
            draw.line([(PAD, y + title_h - 14), (W - PAD, y + title_h - 14)], fill=(226, 216, 205), width=2)
            y += title_h
        else:
            y += 10
        idx = 0
        for row in rows:
            n = len(row)
            x0 = PAD + max(0, (usable - n * item_w) // 2)
            mark_cy = y + time_h + mark_h // 2
            if n:
                draw.line([(x0 + item_w // 2, mark_cy), (x0 + (n - 1) * item_w + item_w // 2, mark_cy)], fill=(226, 200, 186), width=3)
            for i in range(n):
                ev = row[i]
                cx = x0 + i * item_w + item_w // 2
                tm = _clean(ev.get("time") or "")
                if tm:
                    tb = draw.textbbox((0, 0), tm, font=f_time)
                    draw.text((cx - (tb[2] - tb[0]) / 2, y + 2), tm, font=f_time, fill=MUTED)
                draw.ellipse([cx - 8, mark_cy - 8, cx + 8, mark_cy + 8], fill=TERRA)
                draw.ellipse([cx - 3, mark_cy - 3, cx + 3, mark_cy + 3], fill=CREAM)
                ly = y + time_h + mark_h + 2
                for ln in wrapped[idx + i]:
                    lb = draw.textbbox((0, 0), ln, font=f_label)
                    draw.text((cx - (lb[2] - lb[0]) / 2, ly), ln, font=f_label, fill=INK)
                    ly += label_lh
            idx += n
            y += row_h

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ============================================================
# 여행 타임라인 이미지 — 'DAY n + 라벨:시간' 텍스트를 세로 타임라인으로
# ============================================================
def render_timeline_image(text: str, width: int = 620, direction: str = "v") -> bytes:
    """일정 텍스트를 타임라인 PNG(자동 높이)로 그린다. direction='h'면 가로+줄바꿈."""
    import io
    from app.services.timeline import parse_timeline

    days = parse_timeline(text)
    if direction == "h":
        return _timeline_h_png(days, width)
    PAD = 34
    time_w = 78
    line_x = PAD + time_w + 24
    label_x = line_x + 30
    row_h = 48
    title_h = 60
    day_gap = 20
    top = 28

    # 전체 높이 계산
    H = top
    for d in days:
        H += title_h + len(d["events"]) * row_h + day_gap
    H = max(H + 20, 160)
    W = int(width)

    img = _vgradient(PAPER_HI, PAPER).resize((W, H))
    draw = ImageDraw.Draw(img)
    f_day = _font(30)
    f_time = _font(21)
    f_label = _font(23)

    y = top
    for d in days:
        title = _clean(d.get("title") or "")
        if title:
            draw.text((PAD, y + 6), title, font=f_day, fill=TERRA)
            draw.line([(PAD, y + title_h - 14), (W - PAD, y + title_h - 14)], fill=(226, 216, 205), width=2)
        y += title_h

        evs = d["events"]
        if evs:
            first_cy = y + row_h // 2
            last_cy = y + (len(evs) - 1) * row_h + row_h // 2
            draw.line([(line_x, first_cy), (line_x, last_cy)], fill=(226, 200, 186), width=3)
        for ev in evs:
            cy = y + row_h // 2
            tm = _clean(ev.get("time") or "")
            if tm:
                tb = draw.textbbox((0, 0), tm, font=f_time)
                draw.text((line_x - 24 - (tb[2] - tb[0]), cy - (tb[3] - tb[1]) / 2 - tb[1]), tm, font=f_time, fill=MUTED)
            draw.ellipse([line_x - 8, cy - 8, line_x + 8, cy + 8], fill=TERRA)
            draw.ellipse([line_x - 3, cy - 3, line_x + 3, cy + 3], fill=CREAM)
            label = _clean(ev.get("label") or "")
            lb = draw.textbbox((0, 0), label, font=f_label)
            draw.text((label_x, cy - (lb[3] - lb[1]) / 2 - lb[1]), label, font=f_label, fill=INK)
            y += row_h
        y += day_gap

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ============================================================
# 레이아웃 썸네일 — content_blocks(v3) 첫 페이지를 도식 미리보기로 렌더
#   브라우저 없이 Pillow로 블록 구조를 그린다:
#   - 이미지(로컬): 실제 이미지를 넣음 / 원격·없음: 플레이스홀더
#   - 제목(heading): 실제 텍스트를 Pretendard로 (썸네일에서 식별용)
#   - 본문/코드: 글줄을 암시하는 가로선 / 구분선: 테라코타 줄
# ============================================================
_LINE = (214, 206, 197)      # 본문 글줄
_IMG_BG = (234, 228, 221)    # 이미지 플레이스홀더 배경


def _plain(s: str) -> str:
    """Strip HTML tags and entities from ``s`` and collapse whitespace to single spaces."""
    if not s:
        return ""
    s = _re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return " ".join(s.split())


def _hex_rgb(h: str, fallback=(0, 0, 0)):
    """Parse a CSS hex colour (``#rgb`` or ``#rrggbb``, ``#`` optional) into RGB.

    Args:
        h: The colour string; may be ``None``.
        fallback: Value returned when ``h`` cannot be parsed.

    Returns:
        An ``(r, g, b)`` tuple of ints, or ``fallback`` for invalid input.
    """
    try:
        h = (h or "").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:  # noqa: BLE001
        return fallback


def _local_image_path(src: str) -> Optional[Path]:
    """/static/... 로컬 경로만 허용(원격·경로탈출 차단)."""
    if not src or not src.startswith("/static/"):
        return None
    rel = src[len("/static/"):].split("?", 1)[0].split("#", 1)[0]
    try:
        p = (_STATIC_DIR / rel).resolve()
        if p.is_file() and str(p).startswith(str(_STATIC_DIR.resolve())):
            return p
    except Exception:  # noqa: BLE001
        return None
    return None


def _first_page(content_blocks) -> Optional[dict]:
    """Return the first page of a magazine layout in any stored format.

    Accepts the v3 multi-page format (``{"v": 3, "pages": [...]}``), the older
    single-page dict (``{"blocks": [...], "cw": .., "ch": ..}``) and a bare
    list of blocks. Older formats default to a 1200x800 canvas.

    Args:
        content_blocks: The layout as a JSON string or already-decoded value.

    Returns:
        A page dict with at least ``blocks`` (v3 pages are returned as stored),
        or ``None`` if the input is invalid JSON, empty or unrecognised.
    """
    try:
        data = _json.loads(content_blocks) if isinstance(content_blocks, str) else content_blocks
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict) and data.get("v") == 3 and data.get("pages"):
        return data["pages"][0]
    if isinstance(data, dict) and isinstance(data.get("blocks"), list):
        return {"blocks": data["blocks"], "cw": data.get("cw", 1200), "ch": data.get("ch", 800)}
    if isinstance(data, list) and data:
        return {"blocks": data, "cw": 1200, "ch": 800}
    return None


def render_layout_thumbnail(content_blocks, width: int = 600) -> bytes:
    """매거진 레이아웃(content_blocks)의 첫 페이지를 도식 썸네일 PNG로."""
    import io
    page = _first_page(content_blocks)
    cw = (page or {}).get("cw") or 1200
    ch = (page or {}).get("ch") or 800
    try:
        cw = float(cw) or 1200
        ch = float(ch) or 800
    except (TypeError, ValueError):
        cw, ch = 1200, 800
    scale = width / cw
    W = int(round(width))
    H = max(1, int(round(ch * scale)))
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img)

    if not page or not page.get("blocks"):
        # 빈 레이아웃 플레이스홀더
        draw.text((W / 2 - 40, H / 2 - 12), "빈 페이지", font=_font(22), fill=MUTED)
        buf = io.BytesIO(); img.save(buf, format="PNG", optimize=True); return buf.getvalue()

    for b in page["blocks"]:
        if not isinstance(b, dict):
            continue
        x = int(round((b.get("x") or 0) * scale)); y = int(round((b.get("y") or 0) * scale))
        w = int(round((b.get("w") or 0) * scale)); h = int(round((b.get("h") or 0) * scale))
        if w <= 1 or h <= 1:
            continue
        x2, y2 = x + w, y + h
        t = b.get("type")
        if t == "image":
            lp = _local_image_path(b["src"]) if b.get("src") else None
            if lp:
                try:
                    im = Image.open(lp).convert("RGB")
                    im = ImageOps.fit(im, (max(1, w), max(1, h)), Image.LANCZOS)
                    flt = b.get("imgFilter")
                    if flt == "bw":
                        im = ImageOps.grayscale(im).convert("RGB")
                    elif flt == "duotone":
                        im = ImageOps.colorize(ImageOps.grayscale(im), black=(74, 40, 27), white=(247, 236, 226))
                    img.paste(im, (x, y))
                except Exception:  # noqa: BLE001
                    _draw_img_ph(draw, x, y, x2, y2)
            else:
                _draw_img_ph(draw, x, y, x2, y2)
        elif t == "spacer":
            pass
        elif t == "heading":
            _draw_heading(draw, x, y, w, h, _plain(b.get("content", "")))
        elif t == "timeline":
            try:
                src = b.get("tlText") or _plain(b.get("content", ""))
                tl = Image.open(io.BytesIO(render_timeline_image(src, width=max(80, w), direction=b.get("tlDir", "v")))).convert("RGB")
                tl = tl.crop((0, 0, min(tl.width, w), min(tl.height, h)))
                img.paste(tl, (x, y))
            except Exception:  # noqa: BLE001
                _draw_text_lines(draw, x, y, w, h)
        else:
            txt = _plain(b.get("content", ""))
            if not txt and h <= max(10, int(round(28 * scale))):  # 구분선 추정
                draw.rectangle([x, y + h // 2, x2, y + h // 2 + max(2, int(2 * scale))], fill=TERRA)
            else:
                _draw_text_lines(draw, x, y, w, h, dark=(t == "code"))

        if b.get("showBorder"):
            bw = max(1, int(round((b.get("borderWidth") or 1) * scale)))
            draw.rectangle([x, y, x2 - 1, y2 - 1], outline=_hex_rgb(b.get("borderColor"), INK), width=bw)

    buf = io.BytesIO(); img.save(buf, format="PNG", optimize=True); return buf.getvalue()


def _draw_img_ph(draw, x, y, x2, y2):
    """Draw an image placeholder (a tinted box with a sun-and-mountains icon).

    The icon is skipped when the box is smaller than 24 px in either direction.

    Args:
        draw: Drawing context of the thumbnail.
        x: Left edge in pixels.
        y: Top edge in pixels.
        x2: Right edge in pixels (exclusive).
        y2: Bottom edge in pixels (exclusive).
    """
    draw.rectangle([x, y, x2 - 1, y2 - 1], fill=_IMG_BG)
    # 간단한 '산+해' 아이콘으로 이미지임을 표시
    w, h = x2 - x, y2 - y
    if w < 24 or h < 24:
        return
    cx, base = x + w / 2, y2 - h * 0.28
    draw.ellipse([x + w * 0.62, y + h * 0.22, x + w * 0.62 + h * 0.14, y + h * 0.22 + h * 0.14], fill=(205, 196, 186))
    draw.polygon([(x + w * 0.2, base), (x + w * 0.42, base - h * 0.3), (x + w * 0.6, base)], fill=(205, 196, 186))
    draw.polygon([(x + w * 0.45, base), (x + w * 0.63, base - h * 0.22), (x + w * 0.82, base)], fill=(196, 186, 175))


def _draw_heading(draw, x, y, w, h, text):
    """Draw a heading block's text, vertically centred, in up to two lines.

    The font size follows the block height (52%, clamped to 11-40 px). If the
    text is empty after cleaning, a dark bar stands in for it.

    Args:
        draw: Drawing context of the thumbnail.
        x: Block left edge in pixels.
        y: Block top edge in pixels.
        w: Block width in pixels; also the wrap width.
        h: Block height in pixels.
        text: Plain heading text.
    """
    size = max(11, min(int(h * 0.52), 40))
    font = _font(size)
    text = _clean(text) or ""
    if not text:
        draw.rectangle([x, y + h // 2 - size // 3, x + int(w * 0.7), y + h // 2 + size // 3], fill=(60, 52, 46))
        return
    lines = _wrap(draw, text, font, w, 2)
    ly = y + max(0, (h - len(lines) * int(size * 1.2)) // 2)
    for ln in lines:
        draw.text((x, ly), ln, font=font, fill=INK)
        ly += int(size * 1.2)


def _draw_text_lines(draw, x, y, w, h, dark=False):
    """Suggest a text block with horizontal bars standing in for lines of text.

    Body text gets up to 12 light bars, the last one shorter. With ``dark``
    the block is drawn as a code block: a dark box with up to 8 green bars.

    Args:
        draw: Drawing context of the thumbnail.
        x: Block left edge in pixels.
        y: Block top edge in pixels.
        w: Block width in pixels.
        h: Block height in pixels.
        dark: Draw the code-block style instead of body text.
    """
    if dark:  # 코드 블록
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=(44, 40, 38))
        col, pad = (120, 150, 130), int(max(6, w * 0.04))
        gap = 14
        n = max(1, (h - pad * 2) // gap)
        for i in range(int(min(n, 8))):
            lw = w * (0.5 if i % 3 == 2 else 0.78) - pad * 2
            yy = y + pad + i * gap
            if lw > 4:
                draw.rectangle([x + pad, yy, x + pad + int(lw), yy + 4], fill=col)
        return
    pad = int(max(4, w * 0.03))
    gap = 15
    n = max(1, (h - pad) // gap)
    for i in range(int(min(n, 12))):
        last = (i == int(min(n, 12)) - 1)
        lw = w * (0.55 if last else 0.92) - pad * 2
        yy = y + pad + i * gap
        if lw > 4 and yy + 5 < y + h:
            draw.rectangle([x + pad, yy, x + pad + int(lw), yy + 5], fill=_LINE)
