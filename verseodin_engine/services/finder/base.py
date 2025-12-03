from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Set

from .schemas import FindDoc, FindOptions


class Finder(ABC):
    @abstractmethod
    async def find_urls(
        self,
        input_url: str,
        options: Optional[FindOptions] = None,
    ) -> FindDoc:
        """Find URLs starting from input_url using FindOptions, returns FindDoc"""
        ...


class URLProcessor(ABC):
    @abstractmethod
    async def process_url(
        self, url: str, domain: str, depth: int, options: Optional[FindOptions] = None
    ) -> Dict[str, Any]:
        """Process a single URL and extract links using FindOptions"""
        ...

    @abstractmethod
    def extract_links(
        self, html: str, base_url: str, domain: str, options: Optional[FindOptions] = None
    ) -> Set[str]:
        """Extract valid links from HTML content using FindOptions"""
        ...

    @abstractmethod
    async def close(self):
        """Close resources"""
        ...
