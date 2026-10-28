"""Plain text of a post body (Markdown, HTML or both) for previews and reading time."""
import html as html_module
import re

import markdown

from app.services.bilingual import DEFAULT_LANGUAGE, pick_language


def markdown_to_plain(text: str, max_len: int | None = 180, lang: str = DEFAULT_LANGUAGE) -> str:
    """Turn a Markdown/HTML post body into one line of plain text.

    Images, code blocks and inline code are dropped, and each ``{{ko||en}}``
    pair keeps only the ``lang`` side.

    Args:
        text: Markdown or HTML body. ``None`` is treated as empty.
        max_len: Cut the result to this many characters and add ``...``;
            ``None`` keeps all of it.
        lang: ``"ko"`` or ``"en"``, the side of bilingual pairs to keep.

    Returns:
        The text with tags removed, entities decoded and whitespace collapsed.
    """
    text = (text or "").strip()
    if not text:
        return ""

    # 1) 이미지 문법은 미리 제거 (alt/url 노이즈 방지)
    text = re.sub(r'!\[.*?\]\(.*?\)', ' ', text)

    # 2) Markdown -> HTML 정규화
    raw_html = markdown.markdown(text, extensions=['fenced_code', 'tables'])

    # 3) 코드/스크립트/스타일 블록 제거 (카드 미리보기 노이즈 방지)
    raw_html = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', raw_html)
    raw_html = re.sub(r'(?is)<pre[^>]*>.*?</pre>', ' ', raw_html)
    raw_html = re.sub(r'(?is)<code[^>]*>.*?</code>', ' ', raw_html)
    raw_html = pick_language(raw_html, lang)  # 이중 언어 {{ko||en}} 은 한쪽만

    # 4) 태그 제거 -> 엔티티 복원 -> 잔재 태그 재제거
    plain = re.sub(r'<[^>]+>', ' ', raw_html)
    plain = html_module.unescape(plain)
    plain = re.sub(r'<[^>\n]+>', ' ', plain)

    # 5) 남아있는 꺾쇠 제거 (엔티티 복원 후 생긴 태그 조각 방어)
    plain = plain.replace("<", " ").replace(">", " ")

    # 6) 줄바꿈/연속 공백 정리
    plain = re.sub(r'\s+', ' ', plain).strip()

    # 7) 최대 길이 제한
    if max_len is not None and len(plain) > max_len:
        plain = plain[:max_len] + '...'
    return plain
