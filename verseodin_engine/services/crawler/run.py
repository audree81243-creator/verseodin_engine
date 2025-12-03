from pprint import pprint

from decouple import config

from . import CrawlerFactory, CrawlerType, CrawlOptions

if __name__ == "__main__":
    url = "https://www.fotoverweij.nl/sony-cinema-line-fx2"
    proxy = config("PROXY_URL", default=None)
    opts = CrawlOptions(proxy=proxy, timeout_ms=180_000, retries=3)
    factory = CrawlerFactory(default_options=opts)

    c_crawler = factory.build(kind=CrawlerType.CRAWL4AI)
    c_doc = c_crawler.fetch(url=url)
    pprint(c_doc.md)

    # h_crawler = factory.build(kind=CrawlerType.HTTPX)
    # h_doc = h_crawler.fetch(url=url)
    # pprint(h_doc)
