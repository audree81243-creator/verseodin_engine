from __future__ import annotations

import asyncio
import logging
from typing import Optional
from urllib.parse import urlparse

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    ProxyConfig,
)

from .base import Crawler
from .errors import CrawlError
from .schemas import CrawlDoc, CrawlOptions

log = logging.getLogger(__name__)


def _make_proxy_cfg(proxy: str) -> ProxyConfig:
    """Build a ProxyConfig from proxy url"""
    if not proxy:
        raise CrawlError(message="Crawling requires Proxy")

    p = urlparse(proxy)
    if not (p.scheme and p.hostname and p.port):
        raise CrawlError(message="Crawling requires Proxy")

    server = f"{p.scheme}://{p.hostname}:{p.port}"
    return ProxyConfig(server=server, username=p.username or "", password=p.password or "")


class Crawl4AICrawler(Crawler):
    """Init sets defaults (options + proxy). fetch can override both."""

    def __init__(
        self,
        *,
        default_options: Optional[CrawlOptions] = None,
    ) -> None:
        self.default_options = default_options or CrawlOptions()

        log.info(
            "crawl4ai_crawler_init",
            extra={
                "extra": {
                    "default_timeout_ms": self.default_options.timeout_ms,
                    "default_retries": self.default_options.retries,
                }
            },
        )

    # Public API -------------------------------------------------------------
    def fetch(
        self,
        url: str,
        options: Optional[CrawlOptions] = None,
    ) -> CrawlDoc:
        headers = self.default_options.headers
        if options and options.headers is not None:
            headers = options.headers

        timeout_ms = self.default_options.timeout_ms
        if options and options.timeout_ms is not None:
            timeout_ms = options.timeout_ms

        retries = self.default_options.retries
        if options and options.retries is not None:
            retries = options.retries

        proxy = self.default_options.proxy
        if options and options.proxy is not None:
            proxy = options.proxy

        proxy_cfg = _make_proxy_cfg(proxy)

        browser_cfg = BrowserConfig(
            proxy_config=proxy_cfg,
            headless=True,
            verbose=False,
        )

        log.info(
            "fetch_start",
            extra={
                "extra": {
                    "url": url,
                    "timeout_ms": timeout_ms,
                    "retries": retries,
                    "has_headers": bool(headers),
                }
            },
        )

        try:
            result = asyncio.run(
                self._get_md_async(
                    url,
                    headers=headers,
                    timeout_ms=timeout_ms,
                    retries=retries,
                    browser_cfg=browser_cfg,
                )
            )
            log.info(
                "fetch_done",
                extra={
                    "extra": {
                        "url": url,
                        "status": result.status,
                        "success": bool(result.meta.get("success")),
                    }
                },
            )
            return result
        except Exception as e:
            log.exception("fetch_error", extra={"extra": {"url": url}})
            return CrawlDoc(
                url=url,
                status=0,
                md="",
                html="",
                meta={
                    "success": False,
                    "error": f"crawl4ai fetch failed for {url}: {e}",
                    "timeout_ms": timeout_ms,
                },
            )

    async def _get_md_async(
        self,
        url: str,
        *,
        headers: Optional[dict],
        timeout_ms: Optional[int],
        retries: Optional[int],
        browser_cfg: BrowserConfig,
    ) -> CrawlDoc:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            status, md, html = 0, "", ""
            meta = {"success": False, "error": None, "timeout_ms": timeout_ms}
            run_config = CrawlerRunConfig(verbose=False, cache_mode=CacheMode.BYPASS)
            tries = int(retries or 0)
            if tries < 0:
                tries = 0

            for i in range(tries):
                try:
                    this_timeout = None if timeout_ms is None else timeout_ms * (2**i)
                    run_cfg = (
                        run_config.clone(page_timeout=this_timeout)
                        if this_timeout is not None
                        else run_config.clone()
                    )

                    log.info(
                        "attempt_start",
                        extra={
                            "extra": {
                                "url": url,
                                "attempt": i + 1,
                                "of": tries,
                                "timeout_ms": this_timeout,
                            }
                        },
                    )

                    res = await crawler.arun(
                        url=url,
                        config=run_cfg,
                        headers=headers,
                    )

                    status = getattr(res, "status_code", 0) or 0
                    md = getattr(res, "markdown", "") or ""
                    html = getattr(res, "html", "") or ""
                    meta = {
                        "success": bool(getattr(res, "success", False)),
                        "error": getattr(res, "error_message", None),
                        "timeout_ms": this_timeout,
                    }

                    log.info(
                        "attempt_result",
                        extra={
                            "extra": {
                                "url": url,
                                "attempt": i + 1,
                                "status": status,
                                "success": meta["success"],
                            }
                        },
                    )

                    retryable = status in (0, 429) or (500 <= status < 600)
                    if meta["success"] and not retryable:
                        break

                except Exception as e:
                    status, md, html = 0, "", ""
                    meta = {
                        "success": False,
                        "error": str(e),
                        "timeout_ms": (None if timeout_ms is None else timeout_ms * (2**i)),
                    }
                    log.exception(
                        "attempt_exception",
                        extra={"extra": {"url": url, "attempt": i + 1}},
                    )

                # backoff wait between tries
                if i < tries - 1:
                    sleep_s = 0.5 * (2**i)
                    log.info(
                        "backoff_sleep",
                        extra={"extra": {"url": url, "attempt": i + 1, "sleep_s": sleep_s}},
                    )
                    try:
                        await asyncio.sleep(sleep_s)
                    except Exception:
                        pass

            return CrawlDoc(url=url, status=status, md=md, html=html, meta=meta)


if __name__ == "__main__":
    # In non-Django scripts, remember to initialize logging and set a request id
    from logger.config import init_logging
    from logger.context import new_request_id

    init_logging()
    new_request_id()

    from decouple import config

    base_proxy = config("PROXY_URL", None)
    base_opts = CrawlOptions(proxy=base_proxy, timeout_ms=60_000, retries=3)

    crawler = Crawl4AICrawler(default_options=base_opts)

    doc = crawler.fetch(
        "https://wowma.jp/itemlist?at=FP&e_scope=O&non_gr=ex&spe_id=header_search&keyword=candles"
    )
    print(doc)
