"""여행 지도 — 장소 좌표를 OSM 타일로 정적 지도 PNG로 렌더.

입력 형식(한 줄에 한 장소):
    라벨@위도,경도        예) 왕궁@13.7500,100.4914
    라벨                  (좌표 없으면 Nominatim으로 지오코딩, 실패 시 생략)

브라우저/라이브러리 없이 Pillow로 OSM 타일을 받아 이어붙이고 핀을 그린다.
타일 사용량이 적도록 결과를 디스크 캐시(라우터)에서 재사용한다.
"""
from __future__ import annotations

import io
import math
import re
import urllib.parse
import urllib.request
from functools import lru_cache

from PIL import Image, ImageDraw

from app.services.og_image import _font, _clean, TERRA, INK, MUTED, CREAM, PAPER

TILE = 256
_UA = "PlanetKIM-magazine/1.0 (+https://planet-kim; static map)"
_PLACE = re.compile(r"^(.*?)@\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_places(text: str) -> list[dict]:
    """각 줄을 {label, lat, lng} 로. 좌표 없으면 lat/lng=None(지오코딩 대상)."""
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _PLACE.match(line)
        if m:
            out.append({"label": m.group(1).strip(), "lat": float(m.group(2)), "lng": float(m.group(3))})
        else:
            out.append({"label": line, "lat": None, "lng": None})
    return out


@lru_cache(maxsize=512)
def geocode(name: str):
    """장소명 → (lat, lng). 실패 시 None. Nominatim(OSM) 사용."""
    try:
        q = urllib.parse.urlencode({"q": name, "format": "json", "limit": 1})
        req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{q}", headers={"User-Agent": _UA})
        import json
        data = json.loads(urllib.request.urlopen(req, timeout=8).read().decode("utf-8"))
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:  # noqa: BLE001
        return None
    return None


def _lonlat_to_px(lat, lon, z):
    """전역 픽셀 좌표(해당 줌에서)."""
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n * TILE
    la = math.radians(lat)
    y = (1 - math.asinh(math.tan(la)) / math.pi) / 2 * n * TILE
    return x, y


@lru_cache(maxsize=1024)
def _fetch_tile(z, x, y):
    """Download one OSM raster tile, cached in memory (up to 1024 tiles).

    Args:
        z: Zoom level.
        x: Tile column at that zoom.
        y: Tile row at that zoom.

    Returns:
        The tile's PNG bytes, or ``None`` if the coordinates are outside the
        world or the request failed.
    """
    n = 2 ** z
    if x < 0 or y < 0 or x >= n or y >= n:
        return None
    url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        return urllib.request.urlopen(req, timeout=12).read()
    except Exception:  # noqa: BLE001
        return None


def _choose_zoom(pts, w, h):
    """Pick the highest zoom (16 down to 2) at which all points fit in the image.

    A 40 px margin is kept on every side.

    Args:
        pts: ``(lat, lng)`` pairs to show.
        w: Image width in pixels.
        h: Image height in pixels.

    Returns:
        The zoom level: 14 for zero or one point, otherwise 2-16.
    """
    if len(pts) <= 1:
        return 14
    min_lat = min(p[0] for p in pts); max_lat = max(p[0] for p in pts)
    min_lng = min(p[1] for p in pts); max_lng = max(p[1] for p in pts)
    for z in range(16, 1, -1):
        x1, y1 = _lonlat_to_px(max_lat, min_lng, z)
        x2, y2 = _lonlat_to_px(min_lat, max_lng, z)
        if abs(x2 - x1) <= w - 80 and abs(y2 - y1) <= h - 80:
            return z
    return 2


def render_map_png(text: str, width: int = 640, height: int = 420) -> bytes:
    """Render a static map PNG with numbered pins for the places in ``text``.

    Uses the first 30 places (see :func:`parse_places`); places without
    coordinates are geocoded and skipped if that fails. Pins are joined in
    order by a route line, a legend lists up to six places, and the required
    OpenStreetMap attribution is drawn in the top-right corner. Missing tiles
    leave a plain background instead of failing. Makes network requests to
    OSM tile and Nominatim servers.

    Args:
        text: Place list, one ``label@lat,lng`` or ``label`` per line.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        PNG bytes. If no place could be located, a placeholder image asking
        for places is returned instead.
    """
    places = parse_places(text)[:30]   # 타일 요청량 제한
    # 좌표 없는 곳 지오코딩
    pts = []
    for p in places:
        lat, lng = p["lat"], p["lng"]
        if lat is None:
            g = geocode(p["label"])
            if not g:
                continue
            lat, lng = g
        pts.append((lat, lng, p["label"]))

    W, H = int(width), int(height)
    if not pts:
        img = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(img)
        d.text((W / 2 - 90, H / 2 - 12), "지도: 장소를 입력하세요", font=_font(20), fill=MUTED)
        buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()

    z = _choose_zoom([(la, ln) for la, ln, _ in pts], W, H)
    cen_lat = sum(p[0] for p in pts) / len(pts)
    cen_lng = sum(p[1] for p in pts) / len(pts)
    ccx, ccy = _lonlat_to_px(cen_lat, cen_lng, z)
    left = ccx - W / 2
    top = ccy - H / 2

    canvas = Image.new("RGB", (W, H), (233, 229, 222))
    tx0, tx1 = math.floor(left / TILE), math.floor((left + W) / TILE)
    ty0, ty1 = math.floor(top / TILE), math.floor((top + H) / TILE)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            raw = _fetch_tile(z, tx, ty)
            if not raw:
                continue
            try:
                tile = Image.open(io.BytesIO(raw)).convert("RGB")
            except Exception:  # noqa: BLE001
                continue
            canvas.paste(tile, (int(tx * TILE - left), int(ty * TILE - top)))

    # 살짝 밝게(라벨 가독성) + 그리기
    draw = ImageDraw.Draw(canvas, "RGBA")
    # 경로 선(장소 순서대로)
    px = [(_lonlat_to_px(la, ln, z)[0] - left, _lonlat_to_px(la, ln, z)[1] - top) for la, ln, _ in pts]
    if len(px) > 1:
        draw.line(px, fill=(180, 84, 47, 200), width=4, joint="curve")
    f = _font(20)
    for i, (x, y) in enumerate(px, 1):
        # 핀(물방울 대신 번호 원)
        r = 15
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(180, 84, 47, 255), outline=(255, 255, 255, 255), width=3)
        num = str(i)
        tb = draw.textbbox((0, 0), num, font=f)
        draw.text((x - (tb[2] - tb[0]) / 2 - tb[0], y - (tb[3] - tb[1]) / 2 - tb[1]), num, font=f, fill=CREAM)

    # 하단 범례(번호 - 라벨)
    lf = _font(18)
    pad = 10
    legend_lines = [f"{i}. {_clean(lbl)}" for i, (_, _, lbl) in enumerate(pts, 1)]
    lh = 24
    box_h = min(len(legend_lines), 6) * lh + pad * 2
    draw.rectangle([0, H - box_h, W, H], fill=(255, 255, 255, 220))
    yy = H - box_h + pad
    for ln in legend_lines[:6]:
        draw.text((pad, yy), ln, font=lf, fill=INK)
        yy += lh

    # OSM 저작자 표시(필수)
    af = _font(12)
    draw.rectangle([W - 118, 0, W, 16], fill=(255, 255, 255, 180))
    draw.text((W - 116, 1), "© OpenStreetMap", font=af, fill=(90, 80, 70))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
