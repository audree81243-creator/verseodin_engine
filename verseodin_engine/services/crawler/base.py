from typing import Optional, Protocol

from .schemas import CrawlDoc, CrawlOptions


class Crawler(Protocol):
    def fetch(self, url: str, options: Optional[CrawlOptions] = None) -> CrawlDoc: ...
