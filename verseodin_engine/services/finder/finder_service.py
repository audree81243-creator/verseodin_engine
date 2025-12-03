import asyncio
import logging
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from .base import Finder
from .config import (
    EXCLUDED_EXTENSIONS,
    PROXY_DEBUG,
    REQUIRE_PROXY,
)
from .errors import FindError
from .schemas import FindDoc, FindOptions
from .url_processor import URLProcessorService
from .utils import (
    extract_homepage_from_url,
    get_proxy_from_env,
    validate_input_url,
)


class FinderService(Finder):
    def __init__(self, processor=None):
        self.processor = processor or URLProcessorService()
        self.successful_urls: Set[str] = set()
        self.failed_urls: Set[str] = set()
        self.crawled_urls: Set[str] = set()
        self.all_discovered_links: Dict[str, List[str]] = {}
        self.error_details: Dict[str, Dict] = {}
        self.proxy_url: str = None
        self.max_depth_reached: int = 0
        self.max_concurrent_requests: int = 100  # Default value
        self.logger = logging.getLogger("finder_service")

    async def find_urls(
        self,
        input_url: str,
        options: Optional[FindOptions] = None,
    ) -> FindDoc:
        """Find URLs using S2 queue-based recursive approach with logging."""

        # Use options or defaults
        if options is None:
            options = FindOptions()

        # Extract parameters from options (now with defaults in the dataclass)
        max_depth = options.max_depth
        max_urls = options.max_urls
        batch_size = options.batch_size
        max_concurrent_requests = options.max_concurrent_requests

        # Store max_concurrent_requests as instance variable for later use
        self.max_concurrent_requests = max_concurrent_requests

        # Set proxy URL from options or environment
        proxy_url = options.proxy
        self.proxy_url = proxy_url or get_proxy_from_env()

        # Debug proxy configuration
        if PROXY_DEBUG:
            self.logger.info("PROXY DEBUG:")
            self.logger.info(f"  • REQUIRE_PROXY: {REQUIRE_PROXY}")
            self.logger.info(f"  • Proxy URL provided: {'Yes' if proxy_url else 'No'}")
            proxy_from_env = "Yes" if get_proxy_from_env() else "No"
            self.logger.info(f"  • Proxy from config/env: {proxy_from_env}")
            self.logger.info(f"  • Final proxy URL: {self.proxy_url}")

        # Validate proxy if required
        if REQUIRE_PROXY and not self.proxy_url:
            raise FindError(
                "Proxy is required but not configured. "
                "Please set PROXY_URL or PROXY_SERVER/PROXY_USERNAME/PROXY_PASSWORD "
                "in your .env file."
            )

        # Extract domain for validation
        start_url = validate_input_url(input_url)
        homepage_url = extract_homepage_from_url(start_url)
        parsed = urlparse(homepage_url)
        self.base_domain = f"{parsed.scheme}://{parsed.netloc}"
        self.domain = parsed.netloc

        # Display initial banner
        self.logger.info("=" * 80)
        self.logger.info("URL FINDER - ASYNC QUEUE-BASED CRAWLER")
        self.logger.info("=" * 80)
        self.logger.info(f"Target: {max_urls:,} URLs from {homepage_url}")
        self.logger.info(f"Batch size: {batch_size} | Concurrency: {max_concurrent_requests}")
        self.logger.info(f"Max depth: {max_depth}")
        self.logger.info(f"Domain: {self.domain}")

        # Show proxy status
        if self.proxy_url:
            proxy_server = (
                self.proxy_url.split("@")[-1] if "@" in self.proxy_url else self.proxy_url
            )
            self.logger.info(f"Proxy: ✅ Using {proxy_server}")
        else:
            self.logger.info("Proxy: ❌ Not using proxy")

        start_time = time.time()

        # Initialize with homepage URL
        self.successful_urls.add(homepage_url)
        self.logger.info(f"Starting with: {homepage_url}", extra={"extra": {"url": homepage_url}})

        # Create aiohttp session
        connector = aiohttp.TCPConnector(
            limit=max_concurrent_requests,
            limit_per_host=30,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
            ttl_dns_cache=300,
        )

        timeout = aiohttp.ClientTimeout(total=30, connect=10)

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": options.user_agent},
        ) as session:
            # Start recursive crawling from depth 0 (homepage)
            next_depth_urls = []

            for depth in range(0, max_depth + 1):
                self.max_depth_reached = depth  # Track the maximum depth reached
                self.logger.info(f"\nSTARTING DEPTH {depth}")

                if depth == 0:
                    # Depth 0: homepage URL
                    urls_to_crawl = [homepage_url]
                    self.logger.info(f"DEPTH 0 (HOMEPAGE): {homepage_url}")
                else:
                    # Use URLs found in previous depth and apply comprehensive deduplication
                    raw_urls = list(next_depth_urls)
                    if not raw_urls:
                        self.logger.warning(f"No new URLs found for depth {depth}, stopping")
                        break

                    # Apply deduplication BEFORE batching
                    urls_to_crawl = self._deduplicate_urls(raw_urls)

                    # Show deduplication results
                    if len(raw_urls) != len(urls_to_crawl):
                        self.logger.debug(
                            f"Pre-batch deduplication: {len(raw_urls):,} → "
                            f"{len(urls_to_crawl):,} URLs "
                            f"(removed {len(raw_urls) - len(urls_to_crawl):,} duplicates)"
                        )

                self.logger.info(f"DEPTH {depth}: Processing {len(urls_to_crawl):,} URLs")

                # Process this depth and get URLs for next depth
                next_depth_urls = await self._process_depth_with_progress(
                    urls_to_crawl, depth, batch_size, max_urls, session
                )

                self.logger.info(
                    f"DEPTH {depth} COMPLETE: {len(self.successful_urls):,} total successful URLs"
                )

                # Check if target reached
                if len(self.successful_urls) >= max_urls:
                    self.logger.info(
                        f"TARGET REACHED! {len(self.successful_urls):,} URLs found at depth {depth}"
                    )
                    self.logger.info(f"STOPPING CRAWL - Target of {max_urls:,} URLs achieved")
                    break

        # Final results
        total_time = time.time() - start_time
        self._display_final_results(total_time, max_urls)

        # Create and return FindDoc with all collected information
        return FindDoc(
            input_url=input_url,
            homepage_url=homepage_url,
            domain=self.domain,
            urls=self.successful_urls,
            total_found=len(self.successful_urls),
            max_depth_reached=self.max_depth_reached,
            successful_crawls=len(self.successful_urls),
            failed_crawls=len(self.error_details),
            processing_time=total_time,
            meta={
                "options_used": {
                    "max_depth": max_depth,
                    "max_urls": max_urls,
                    "batch_size": batch_size,
                    "proxy": self.proxy_url,
                },
                "error_details": self.error_details,
                "crawled_urls": list(self.crawled_urls),
            },
        )

    async def _process_depth_with_progress(
        self,
        urls_to_crawl: List[str],
        current_depth: int,
        batch_size: int,
        max_urls: int,
        session: aiohttp.ClientSession,
    ) -> List[str]:
        """Process URLs at current depth with progress bars."""

        # Prepare batches
        batches = [
            urls_to_crawl[i : i + batch_size] for i in range(0, len(urls_to_crawl), batch_size)
        ]
        next_depth_urls = []

        # Track metrics for final summary
        depth_start_time = time.time()
        total_processed = 0
        total_successful = 0
        total_new_urls = 0

        # Process batches
        for batch_idx, batch in enumerate(batches, 1):
            batch_start_time = time.time()

            # Display batch info
            self.logger.info(
                f"D{current_depth} BATCH {batch_idx}/{len(batches)}: Processing {len(batch)} URLs"
            )

            # Process batch concurrently
            batch_results = await self._process_batch(batch, current_depth, session)

            # Process results
            batch_new_urls = []
            batch_successful = 0
            batch_failed = 0

            for result in batch_results:
                total_processed += 1

                if result["status"] == "success":
                    batch_successful += 1
                    total_successful += 1
                    self.successful_urls.add(result["url"])

                    # Collect new URLs for next depth (avoid duplicates)
                    for new_url in result["new_urls"]:
                        if (
                            new_url not in self.successful_urls
                            and new_url not in self.failed_urls
                            and new_url not in batch_new_urls
                        ):
                            batch_new_urls.append(new_url)
                            total_new_urls += 1
                else:
                    batch_failed += 1
                    self.failed_urls.add(result["url"])

            # Add new URLs to next depth (deduplication will be done at start of next depth)
            next_depth_urls.extend(batch_new_urls)

            # Batch completion summary with timing
            batch_time = time.time() - batch_start_time
            self.logger.info(f"Batch {batch_idx} complete in {batch_time:.1f}s:")
            self.logger.info(f"   • Processed: {len(batch)} URLs")
            self.logger.info(f"   • Successful: {batch_successful}")
            if batch_failed > 0:
                self.logger.warning(f"   • Failed: {batch_failed}")
            self.logger.info(f"   • New URLs found: {len(batch_new_urls)}")
            extra_data = {
                "batch_idx": batch_idx,
                "successful_count": batch_successful,
                "new_urls_count": len(batch_new_urls),
            }
            self.logger.info(
                f"   • Total successful: {len(self.successful_urls)}", extra={"extra": extra_data}
            )

            # Stop if target reached
            if len(self.successful_urls) >= max_urls:
                self.logger.info(f"Target reached! Stopping at {len(self.successful_urls):,} URLs")
                break

        # Depth summary
        depth_time = time.time() - depth_start_time
        self.logger.info(f"DEPTH {current_depth} SUMMARY:")
        self.logger.info(f"   • Total processed: {total_processed}")
        self.logger.info(f"   • Successful: {total_successful}")
        self.logger.info(f"   • New URLs for next depth: {len(next_depth_urls)}")
        self.logger.info(f"   • Overall successful URLs: {len(self.successful_urls)}")
        self.logger.info(f"   • Time taken: {depth_time:.1f}s")

        # Return URLs for next depth (deduplication will be applied at start of next depth)
        return next_depth_urls[
            : max_urls - len(self.successful_urls)
        ]  # Limit to remaining needed URLs

    async def _process_batch(
        self,
        batch: list,
        depth: int,
        session: aiohttp.ClientSession,
    ) -> list:
        """Process a batch of URLs concurrently."""

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        async def crawl_url_with_semaphore(url):
            async with semaphore:
                try:
                    result = await self._crawl_url(url, depth, session)
                    return result
                except Exception as e:
                    return {"url": url, "status": "error", "new_urls": [], "error": str(e)}

        # Process all URLs in batch concurrently
        results = await asyncio.gather(
            *[crawl_url_with_semaphore(url) for url in batch], return_exceptions=True
        )

        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    {"url": batch[i], "status": "error", "new_urls": [], "error": str(result)}
                )
            else:
                processed_results.append(result)

        return processed_results

    async def _crawl_url(self, url: str, depth: int, session: aiohttp.ClientSession) -> dict:
        """Crawl a single URL with error handling and result formatting."""

        try:
            # Get proxy - use instance proxy or environment proxy
            proxy = self.proxy_url or get_proxy_from_env()

            async with session.get(url, proxy=proxy) as response:
                if response.status != 200:
                    return {
                        "url": url,
                        "status": "failed",
                        "new_urls": [],
                        "error": f"HTTP {response.status}",
                    }

                html_content = await response.text()

                # Extract links using BeautifulSoup
                soup = BeautifulSoup(html_content, "html.parser")

                # Find all anchor tags
                new_urls = []
                for link in soup.find_all("a", href=True):
                    href = link.get("href")
                    if href:
                        # Convert relative URLs to absolute
                        absolute_url = urljoin(url, href)

                        # Validate domain
                        if self._is_valid_domain_url(absolute_url):
                            new_urls.append(absolute_url)

                # Remove duplicates
                new_urls = list(set(new_urls))

                return {"url": url, "status": "success", "new_urls": new_urls}

        except asyncio.TimeoutError:
            return {"url": url, "status": "failed", "new_urls": [], "error": "Timeout"}
        except Exception as e:
            return {"url": url, "status": "failed", "new_urls": [], "error": str(e)}

    def _is_valid_domain_url(self, url: str) -> bool:
        """Check if URL belongs to the target domain and is not excluded."""
        try:
            parsed = urlparse(url)

            # Check domain match
            if parsed.netloc != self.domain:
                return False

            # Check for excluded extensions
            path = parsed.path.lower()
            for ext in EXCLUDED_EXTENSIONS:
                if path.endswith(ext):
                    return False

            return True
        except Exception:
            return False

    def _display_final_results(self, total_time: float, max_urls: int):
        """Display final results with comprehensive metrics via logging."""

        self.logger.info("=" * 80)
        self.logger.info("CRAWLING COMPLETE")
        self.logger.info("=" * 80)

        # Calculate final statistics
        total_attempted = len(self.successful_urls) + len(self.failed_urls)
        success_rate = (
            (len(self.successful_urls) / total_attempted) * 100 if total_attempted > 0 else 0
        )
        avg_speed = len(self.successful_urls) / total_time if total_time > 0 else 0

        # Main summary
        self.logger.info("Final Crawling Summary:")
        self.logger.info(f"  • Total URLs Found: {len(self.successful_urls):,}")
        self.logger.info(
            f"  • Successfully Crawled: {len(self.successful_urls):,} ({success_rate:.1f}%)"
        )
        failed_percentage = (
            (len(self.failed_urls) / total_attempted) * 100 if total_attempted > 0 else 0
        )
        self.logger.info(f"  • Failed URLs: {len(self.failed_urls):,} ({failed_percentage:.1f}%)")
        self.logger.info(f"  • Target URLs: {max_urls:,}")

        target_achievement = "Yes" if len(self.successful_urls) >= max_urls else "No"
        target_percentage = (len(self.successful_urls) / max_urls) * 100
        self.logger.info(f"  • Target Achievement: {target_achievement} ({target_percentage:.1f}%)")

        # Performance summary
        total_hours = int(total_time // 3600)
        total_minutes = int((total_time % 3600) // 60)
        total_seconds = int(total_time % 60)

        self.logger.info("Performance Summary:")
        time_str = f"{total_hours:02d}h {total_minutes:02d}m {total_seconds:02d}s"
        self.logger.info(f"  • Total Time: {time_str}")
        self.logger.info(f"  • Average Speed: {avg_speed:.2f} URLs/second")
        self.logger.info(f"  • URLs per Minute: {avg_speed * 60:.1f}")
        self.logger.info(f"  • Concurrent Requests: {self.max_concurrent_requests}")
        self.logger.info("  • Batch Processing: Enabled")

        # Sample URLs
        if self.successful_urls:
            urls_list = sorted(list(self.successful_urls))
            self.logger.info("Sample URLs (first 10):")

            sample_urls = urls_list[:10]
            for i, url in enumerate(sample_urls, 1):
                self.logger.info(f"  {i:2d}. {url}")

            if len(urls_list) > 10:
                self.logger.info(f"  ... and {len(urls_list) - 10:,} more URLs")

        # Success rate message
        if success_rate >= 95:
            self.logger.info(
                f"Excellent success rate! {success_rate:.1f}% of URLs crawled successfully."
            )
        elif success_rate >= 80:
            self.logger.warning(
                f"Good success rate. {success_rate:.1f}% of URLs crawled successfully."
            )
        else:
            self.logger.error(
                f"Low success rate. {success_rate:.1f}% of URLs crawled successfully."
            )

        self.logger.info(
            "Ready for next operation",
            extra={
                "extra": {
                    "total_urls": len(self.successful_urls),
                    "success_rate": success_rate,
                    "total_time": total_time,
                    "avg_speed": avg_speed,
                }
            },
        )

    def _deduplicate_urls(self, urls_list: List[str]) -> List[str]:
        """
        Comprehensive URL deduplication with HTTP/HTTPS preference.

        Rules:
        1. Remove URLs already in successful_urls or failed_urls
        2. Remove exact duplicates
        3. Remove URLs with fragments (anchor links like #tmp_header)
        4. If both HTTP and HTTPS versions exist, prefer HTTPS
        5. Only keep HTTP if HTTPS version doesn't exist
        """
        # Convert to set for faster lookups
        all_processed = self.successful_urls.union(self.failed_urls)

        # First pass: remove already processed URLs, exact duplicates, and fragment URLs
        unique_urls = []
        seen_urls = set()

        for url in urls_list:
            # Skip URLs with fragments (anchor links)
            parsed = urlparse(url)
            if parsed.fragment:
                continue  # Skip URLs with fragments like #tmp_header

            if url not in all_processed and url not in seen_urls:
                unique_urls.append(url)
                seen_urls.add(url)

        # Second pass: Handle HTTP/HTTPS preference
        # Group URLs by their path (without scheme)
        url_groups = {}
        for url in unique_urls:
            parsed = urlparse(url)
            # Create a key without the scheme
            path_key = f"{parsed.netloc}{parsed.path}"
            if parsed.query:
                path_key += f"?{parsed.query}"
            if parsed.fragment:
                path_key += f"#{parsed.fragment}"

            if path_key not in url_groups:
                url_groups[path_key] = []
            url_groups[path_key].append(url)

        # Third pass: Apply HTTP/HTTPS preference
        final_urls = []
        for _path_key, url_group in url_groups.items():
            if len(url_group) == 1:
                # Only one URL for this path, keep it
                final_urls.append(url_group[0])
            else:
                # Multiple URLs for same path, apply preference
                https_urls = [url for url in url_group if url.startswith("https://")]
                http_urls = [url for url in url_group if url.startswith("http://")]

                if https_urls:
                    # Prefer HTTPS - pick the first HTTPS URL
                    final_urls.append(https_urls[0])
                elif http_urls:
                    # No HTTPS available, use HTTP
                    final_urls.append(http_urls[0])
                else:
                    # Neither HTTP nor HTTPS (edge case), pick first
                    final_urls.append(url_group[0])

        return final_urls


async def find_all_urls(
    input_url: str,
    max_depth: int = 12,
    max_urls: int = 50000,
    batch_size: int = 100,
    proxy_url: str = None,
) -> list:
    """Async convenience function for external usage - returns list instead of set"""
    finder = FinderService()
    try:
        # Create FindOptions from individual parameters for backward compatibility
        options = FindOptions(
            max_depth=max_depth, max_urls=max_urls, batch_size=batch_size, proxy=proxy_url
        )

        find_doc = await finder.find_urls(input_url, options)
        return list(find_doc.urls)  # Convert set to list for JSON serialization
    finally:
        await finder.processor.close()


async def main(url: str, max_depth: int, max_urls: int, proxy_url: str):
    """Main function that takes URL, max depth, max URLs, and proxy as arguments."""
    finder = FinderService()
    try:
        # Create FindOptions from individual parameters for backward compatibility
        options = FindOptions(
            max_depth=max_depth, max_urls=max_urls, batch_size=100, proxy=proxy_url
        )

        find_doc = await finder.find_urls(url, options)
        return list(find_doc.urls)
    finally:
        await finder.processor.close()


if __name__ == "__main__":
    import asyncio

    from decouple import config

    from logger.config import init_logging
    from logger.context import new_request_id

    # Get parameters from environment variables with defaults from FindOptions
    default_options = FindOptions()
    url = config("FINDER_URL", default="https://example.com")
    max_depth = config("FINDER_MAX_DEPTH", default=default_options.max_depth, cast=int)
    max_urls = config("FINDER_MAX_URLS", default=default_options.max_urls, cast=int)
    proxy_url = config("PROXY_URL", default=None)

    init_logging()
    new_request_id()
    logger = logging.getLogger("finder_service")

    logger.info(f"Starting finder with URL: {url}")
    logger.info(f"Max depth: {max_depth}, Max URLs: {max_urls}")

    urls = asyncio.run(main(url, max_depth, max_urls, proxy_url))
    logger.info(f"Found {len(urls)} URLs")
