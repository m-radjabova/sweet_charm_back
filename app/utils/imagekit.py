from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import settings


def build_imagekit_webp_url(url: str | None, *, width: int, quality: int = 80) -> str | None:
    if not url:
        return url
    if "tr=" in url or not _is_imagekit_url(url):
        return url

    separator = "&" if "?" in url else "?"
    return f"{url}{separator}tr=w-{width},q-{quality},f-webp"


def _is_imagekit_url(url: str) -> bool:
    endpoint = settings.IMAGEKIT_URL_ENDPOINT
    if endpoint and url.startswith(endpoint):
        return True

    host = urlparse(url).netloc.lower()
    return host.endswith("imagekit.io")
