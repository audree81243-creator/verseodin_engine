Minimal, pluggable web crawler with two engines (**httpx**, **crawl4ai**), a shared protocol, and a small Celery/Django pipeline for batch crawling.

## TL;DR

```python
from decouple import config
from services.crawler import CrawlerFactory, CrawlerType, CrawlOptions

proxy = config("PROXY_URL")
opts = CrawlOptions(proxy=proxy, timeout_ms=60000, retries=3)

factory = CrawlerFactory(default_options=opts)
crawler = factory.build(CrawlerType.HTTPX)  # or CrawlerType.CRAWL4AI
doc = crawler.fetch("https://example.com")

print(doc.status, doc.meta.get("success"))
print(doc.md[:400])
```

---

## Key Types

- **CrawlOptions**
  - `proxy: str | None` (required here). Example: `http://user:pass@host:8080`
  - `headers: dict | None` (defaults to a modern browser UA)
  - `timeout_ms: int | None` (default 60000)
  - `retries: int | None` (default 3)

- **CrawlDoc**
  - `url: str`
  - `status: int`
  - `md: str` (primary output)
  - `html: str | None`
  - `meta: dict` (e.g., \`success\`, \`error\`, \`used_legacy_tls\`, \`timeout_ms\`)

- **Crawler protocol**
  - `fetch(url: str, options: CrawlOptions | None) -> CrawlDoc`

---

## Crawlers

- **HttpxCrawler**
  - Fast HTTP fetch + `markdownify` conversion
  - Retries on `0`, `429`, and `5xx`
  - Detects TLS renegotiation issue; auto-fallback with legacy TLS (`meta["used_legacy_tls"]`)

- **Crawl4AICrawler**
  - Headless browser via `crawl4ai` (JS-rendered pages)
  - Per-attempt timeout grows: `timeout_ms * 2**i`
  - Retries on `0`, `429`, and `5xx`
  - Add `delay_before_return_html` option if you want to wait for js to render

Pick:
- Static/simple → **Httpx**
- JS/dynamic → **Crawl4AI**

---

## Factory

```python
from services.crawler import CrawlerFactory, CrawlerType, CrawlOptions

factory = CrawlerFactory(default_options=CrawlOptions(proxy="http://u:p@h:8080"))
crawler = factory.build(kind=CrawlerType.CRAWL4AI)

# Override at build:
crawler = factory.build(
    kind="httpx",
    options={"retries": 5, "timeout_ms": 120000},  # Mapping -> CrawlOptions
    headers={"User-Agent": "my-bot/1.0"}           # Any CrawlOptions field can be overridden
)
```

---

## Celery/Django (very brief)

- **`crawler.url_crawler`**: claims an `InputState`, grabs up to `CRAWLER_MAX_URLS_PER_RUN` `URL.NEW`, splits into batches of 25, fires **`crawler.crawl_batch`** group + chord to **`crawler.finalize_batches`**.
- **Success rule**: `meta.success and 200 <= status < 400` → `URLStatus.CRAWLED`, else `FAILED`. Data saved as `{"md","html","meta"}`.
- Requires on `InputState`: `url_crawler_strategy` in {`HTTPX`, `CRAWL4AI`} and `url_crawler_proxy` (mandatory).

---

## Config

- Env: `PROXY_URL` (e.g. `http://user:pass@host:port`)
- Django setting: `CRAWLER_MAX_URLS_PER_RUN` (int, optional)

---

## Tiny Script

```bash
export PROXY_URL="http://user:pass@host:port"
python -m services.crawler.run
```

