from enum import Enum
from typing import Dict, Mapping, Optional, Type, Union

from .base import Crawler
from .crawl4ai_crawler import Crawl4AICrawler
from .errors import CrawlError
from .httpx_crawler import HttpxCrawler
from .schemas import CrawlOptions


class CrawlerType(str, Enum):
    HTTPX = "httpx"
    CRAWL4AI = "crawl4ai"


class CrawlerFactory:
    """Stateful factory for creating crawler instances."""

    def __init__(self, default_options: Optional[CrawlOptions] = None):
        self.default_options = default_options or CrawlOptions()
        self._registry: Dict[CrawlerType, Type[Crawler]] = {
            CrawlerType.HTTPX: HttpxCrawler,
            CrawlerType.CRAWL4AI: Crawl4AICrawler,
        }

    def build(
        self,
        kind: Union[CrawlerType, str] = CrawlerType.HTTPX,
        *,
        options: Optional[Union[CrawlOptions, Mapping]] = None,
        **overrides,
    ) -> Crawler:
        # normalize kind
        if isinstance(kind, str):
            kind = CrawlerType(kind.lower())
        cls = self._registry.get(kind)
        if cls is None:
            raise CrawlError(f"No crawler registered for {kind}")

        opts = options or self.default_options
        if isinstance(opts, Mapping):
            opts = CrawlOptions(**opts)
        for k, v in overrides.items():
            if hasattr(opts, k):
                setattr(opts, k, v)

        return cls(default_options=opts)
