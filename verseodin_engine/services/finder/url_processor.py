import asyncio
from typing import Any, Dict, Optional, Set
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from .base import URLProcessor
from .config import EXCLUDED_EXTENSIONS
from .schemas import FindOptions
from .utils import get_proxy_from_env


class URLProcessorService(URLProcessor):
    """Async URL processor for extracting links from web pages"""

    def __init__(self, options: Optional[FindOptions] = None):
        self.session = None
        self.options = options  # Don't create default FindOptions here

    async def _get_session(self) -> aiohttp.ClientSession:
        """Create aiohttp session with proxy configuration"""
        if self.session is None:
            get_proxy_from_env()  # Get proxy but don't store unused variable

            # Use default values if options not provided
            max_concurrent_requests = self.options.max_concurrent_requests if self.options else 100
            request_timeout = self.options.request_timeout if self.options else 30
            user_agent = (
                self.options.user_agent
                if self.options
                else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            # Create connector with optimized settings
            connector = aiohttp.TCPConnector(
                limit=max_concurrent_requests,
                limit_per_host=30,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
                ttl_dns_cache=300,
            )

            timeout = aiohttp.ClientTimeout(total=request_timeout, connect=10)

            self.session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, headers={"User-Agent": user_agent}
            )
        return self.session

    async def process_url(
        self, url: str, domain: str, depth: int, options: Optional[FindOptions] = None
    ) -> Dict[str, Any]:
        """Process a single URL and extract links asynchronously"""
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    links = self.extract_links(html, url, domain, options)
                    return {
                        "success": True,
                        "status_code": response.status,
                        "links": links,
                        "links_count": len(links),
                    }
                else:
                    # Try to extract links even from error pages
                    try:
                        html = await response.text()
                        links = self.extract_links(html, url, domain)
                        return {
                            "success": False,
                            "status_code": response.status,
                            "error": f"HTTP {response.status}",
                            "links": links,
                            "links_count": len(links),
                        }
                    except Exception:
                        return {
                            "success": False,
                            "status_code": response.status,
                            "error": f"HTTP {response.status}",
                            "links": set(),
                            "links_count": 0,
                        }
        except asyncio.TimeoutError:
            return {"success": False, "error": "timeout", "links": set(), "links_count": 0}
        except Exception as e:
            return {"success": False, "error": str(e), "links": set(), "links_count": 0}

    def extract_links(
        self, html: str, base_url: str, domain: str, options: Optional[FindOptions] = None
    ) -> Set[str]:
        """Extract valid links from HTML content"""
        try:
            # Use lxml parser if available, fallback to html.parser
            try:
                soup = BeautifulSoup(html, "lxml")
            except Exception:
                soup = BeautifulSoup(html, "html.parser")

            links = set()

            # Extract from a, area, link tags
            for tag in soup.find_all(["a", "area", "link"], href=True):
                href = tag.get("href", "").strip()
                if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    absolute_url = urljoin(base_url, href)
                    if self._is_valid_url_for_domain(absolute_url, domain, options):
                        links.add(absolute_url)

            return links

        except Exception:
            return set()

    def _is_valid_url_for_domain(
        self, url: str, domain: str, options: Optional[FindOptions] = None
    ) -> bool:
        """Check if URL is valid for the target domain"""
        try:
            parsed = urlparse(url)

            # Use excluded extensions from options or default config
            excluded_exts = (
                options.excluded_extensions
                if options and options.excluded_extensions
                else EXCLUDED_EXTENSIONS
            )

            # Check same domain requirement
            require_same_domain = (
                options.require_same_domain
                if options and options.require_same_domain is not None
                else True
            )  # Default to True

            domain_valid = parsed.netloc == domain if require_same_domain else True

            return (
                domain_valid
                and parsed.scheme in ["http", "https"]
                and not any(url.lower().endswith(ext) for ext in excluded_exts)
            )
        except Exception:
            return False

    async def close(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
