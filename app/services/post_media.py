"""Media found in a post body: the first image, used as a card thumbnail."""
import html as html_module
import re


def extract_first_image(text: str):
    """Find the URL of the first image in a post body.

    Looks, in order, for a Markdown image ``![alt](url)``, an ``<img>`` tag
    (``src`` or ``data-src``, quoted or not) and an inline
    ``background-image: url(...)``.

    Args:
        text: Markdown or HTML body.

    Returns:
        The URL with HTML entities decoded, or None when there is no image.
    """
    if not text:
        return None

    # 1) Markdown 이미지
    md_match = re.search(r'!\[[^\]]*]\(([^)]+)\)', text)
    if md_match:
        md_url = md_match.group(1).strip()
        # ![alt](url "title") 형태 대응: 첫 토큰만 URL로 사용
        md_url = md_url.split()[0].strip("<>")
        if md_url:
            return html_module.unescape(md_url)

    # 2) HTML 이미지 태그 (src / data-src)
    html_match = re.search(
        r'<img[^>]+(?:src|data-src)\s*=\s*["\']([^"\']+)["\']',
        text,
        flags=re.IGNORECASE,
    )
    if html_match:
        return html_module.unescape(html_match.group(1).strip())

    # 2-1) 따옴표 없는 속성값 fallback
    html_unquoted_match = re.search(
        r'<img[^>]+(?:src|data-src)\s*=\s*([^\s>]+)',
        text,
        flags=re.IGNORECASE,
    )
    if html_unquoted_match:
        return html_module.unescape(html_unquoted_match.group(1).strip())

    # 3) inline background-image
    bg_match = re.search(
        r'background-image\s*:\s*url\((["\']?)(.*?)\1\)',
        text,
        flags=re.IGNORECASE,
    )
    if bg_match and bg_match.group(2).strip():
        return html_module.unescape(bg_match.group(2).strip())

    return None
