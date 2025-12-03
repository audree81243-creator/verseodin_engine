from __future__ import annotations

import logging
import ssl
import time
from typing import Optional

import httpx
from markdownify import markdownify

from .base import Crawler
from .errors import CrawlError
from .schemas import CrawlDoc, CrawlOptions

log = logging.getLogger(__name__)


class HttpxCrawler(Crawler):
    """Init sets defaults (options + proxy). fetch can override both."""

    def __init__(
        self,
        *,
        default_options: Optional[CrawlOptions] = None,
    ) -> None:
        self.default_options = default_options or CrawlOptions()

        log.info(
            "httpx_crawler_init",
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
        proxy: Optional[str] = None,
        options: Optional[CrawlOptions] = None,
    ) -> CrawlDoc:
        # Headers
        headers = self.default_options.headers or {"User-Agent": "extraction-kit/1.0"}
        if options and options.headers is not None:
            headers = options.headers

        # Retries
        retries = self.default_options.retries
        if options and options.retries is not None:
            retries = options.retries

        # Proxy
        proxy = self.default_options.proxy
        if options and options.proxy is not None:
            proxy = options.proxy

        if not proxy:
            raise CrawlError(message="Crawling requires proxy")

        use_client = httpx.Client(follow_redirects=True, proxy=proxy)

        ctx = ssl.create_default_context()
        # Some OpenSSL builds on runners do not expose OP_LEGACY_SERVER_CONNECT; guard it.
        if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        legacy_client = httpx.Client(follow_redirects=True, proxy=proxy, verify=ctx)

        log.info(
            "fetch_start",
            extra={
                "extra": {
                    "url": url,
                    "retries": retries,
                    "has_headers": bool(headers),
                }
            },
        )

        status, md, html = 0, "", ""
        meta = {"success": False, "error": None, "used_legacy_tls": False}

        tries = int(retries or 0)
        if tries < 0:
            tries = 0

        for i in range(tries):
            used_legacy = False
            try:
                log.info(
                    "attempt_start",
                    extra={
                        "extra": {
                            "url": url,
                            "attempt": i + 1,
                            "of": tries,
                        }
                    },
                )

                try:
                    r = use_client.get(url, headers=headers)
                except Exception as e:
                    if self._is_legacy_reneg_error(e):
                        try:
                            r = legacy_client.get(url, headers=headers)
                            used_legacy = True
                        except Exception as e2:
                            raise e2
                    else:
                        raise

                status = getattr(r, "status_code", 0) or 0
                retryable = status in (0, 429) or (500 <= status < 600)

                r.raise_for_status()

                html = r.text or ""
                md = markdownify(html) if html else ""
                meta = {
                    "success": True,
                    "error": None,
                    "used_legacy_tls": used_legacy,
                }

                log.info(
                    "attempt_result",
                    extra={
                        "extra": {
                            "url": url,
                            "attempt": i + 1,
                            "status": status,
                            "success": meta["success"],
                            "used_legacy_tls": used_legacy,
                        }
                    },
                )

                if meta["success"] and not retryable:
                    break

            except Exception as e:
                status, md, html = 0, "", ""
                meta = {
                    "success": False,
                    "error": str(e),
                    "used_legacy_tls": used_legacy,
                }
                log.exception(
                    "attempt_exception",
                    extra={"extra": {"url": url, "attempt": i + 1, "used_legacy_tls": used_legacy}},
                )

            # Backoff between attempts
            if i < tries - 1:
                sleep_s = 0.5 * (2**i)
                log.info(
                    "backoff_sleep",
                    extra={"extra": {"url": url, "attempt": i + 1, "sleep_s": sleep_s}},
                )
                try:
                    time.sleep(sleep_s)
                except Exception:
                    pass

        log.info(
            "fetch_done",
            extra={"extra": {"url": url, "status": status, "success": bool(meta.get("success"))}},
        )

        try:
            use_client.close()
            legacy_client.close()
        except Exception:
            pass

        if not meta.get("success"):
            meta.setdefault("error", f"Failed to fetch after {tries} attempt(s)")

        return CrawlDoc(url=url, status=status, md=md, html=html, meta=meta)

    # Internal ---------------------------------------------------------------
    def _is_legacy_reneg_error(self, exc: BaseException) -> bool:
        """Check if the underlying cause is ssl.SSLError with the legacy renegotiation issue."""
        err_token = "UNSAFE_LEGACY_RENEGOTIATION_DISABLED"
        seen = set()
        e = exc
        while e and id(e) not in seen:
            seen.add(id(e))
            if isinstance(e, ssl.SSLError) and err_token in str(e):
                return True
            e = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
        return False


if __name__ == "__main__":
    # In non-Django scripts, remember to initialize logging and set a request id
    # from logger.config import init_logging
    # from logger.context import new_request_id

    # init_logging()
    # new_request_id()
    from decouple import config

    base_proxy = config("PROXY_URL", None)
    base_opts = CrawlOptions(retries=3)

    crawler = HttpxCrawler(proxy=base_proxy, default_options=base_opts)

    doc = crawler.fetch(
        "https://www.yodobashi.com/",
    )
    print(doc)
