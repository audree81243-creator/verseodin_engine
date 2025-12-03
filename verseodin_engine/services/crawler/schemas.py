from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from decouple import config

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@dataclass
class CrawlOptions:
    proxy: Optional[str] = config("PROXY_URL", default=None)
    headers: Optional[Dict[str, str]] = field(default_factory=lambda: DEFAULT_HEADERS.copy())
    timeout_ms: Optional[int] = 60_000
    retries: Optional[int] = 3


@dataclass
class CrawlDoc:
    url: str
    status: int
    md: str  # REQUIRED (primary input to LLM)
    html: Optional[str] = None  # Optional (tables/microdata)
    meta: Dict[str, Any] = field(default_factory=dict)
