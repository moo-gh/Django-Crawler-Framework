import re
from typing import Any

TELEGRAM_MAX_PHOTOS = 10
TELEGRAM_CAPTION_LIMIT = 1024

_TRAILING_CACHE_BUST_RE = re.compile(
    r"\.(webp|jpg|jpeg|png)(\d+)$",
    re.IGNORECASE,
)


def _clean_image_url(url: str) -> str:
    """Strip query strings and cache-busting digits glued onto the file extension."""
    url = url.strip().split("?")[0].split("#")[0]
    if url.startswith("//"):
        url = f"https:{url}"
    return _TRAILING_CACHE_BUST_RE.sub(r".\1", url)


def normalize_image_urls(raw: Any) -> list[str]:
    """Normalize image field values from Redis/meta-structure into unique http(s) URLs."""
    if not raw:
        return []

    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                import json

                raw = json.loads(text)
            except (ValueError, TypeError):
                raw = [part.strip() for part in re.split(r"[\n,]", text) if part.strip()]
        else:
            raw = [part.strip() for part in re.split(r"[\n,]", text) if part.strip()]

    if not isinstance(raw, (list, tuple)):
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        url = _clean_image_url(item)
        if not url.startswith("http"):
            continue
        if "webp_thumbnail" in url or "/thumbnails/" in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= TELEGRAM_MAX_PHOTOS:
            break
    return urls
