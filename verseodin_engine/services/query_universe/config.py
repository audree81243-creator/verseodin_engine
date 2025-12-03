# Query Universe Configuration
from decouple import config

# Processing defaults
DEFAULT_MAX_URLS_TO_CRAWL = config("QUERY_UNIVERSE_MAX_URLS", default=100, cast=int)
DEFAULT_ENABLE_LLM = config("QUERY_UNIVERSE_ENABLE_LLM", default=True, cast=bool)

# Proxy Configuration
PROXY_URL = config("PROXY_URL", default=None)

# Maximum pages to pass to crawler
MAX_PAGES_TO_CRAWLER = 5

# Priority pages configuration - pages to prioritize for crawling
PRIORITY_PAGE_PATTERNS = [
    # Homepage (always first)
    ("homepage", ["/", ""]),
    
    # About pages
    ("about", [
        "/about", "/about-us", "/about_us", "/aboutus",
        "/company", "/who-we-are", "/our-story"
    ]),
    
    # FAQ pages
    ("faq", [
        "/faq", "/faqs", "/frequently-asked-questions",
        "/help", "/support"
    ]),
    
    # Sitemap
    ("sitemap", [
        "/sitemap.xml", "/sitemap", "/site-map", "/sitemap.html"
    ]),
    
    # Product pages
    ("product", [
        "/products", "/product", "/services", "/service",
        "/solutions", "/offerings", "/pricing"
    ]),
    
    # Blog/News pages
    ("blog", [
        "/blog", "/blogs", "/news", "/articles",
        "/insights", "/resources", "/stories", "/case-study"
    ]),
]

# LLM prompt templates
DEFAULT_LLM_PROMPT_TEMPLATE = """
Based on the following content from {url}, please answer this query: {query}

Content:
{content}

Please provide a comprehensive answer.
"""

# Logging
QUERY_UNIVERSE_DEBUG = config("QUERY_UNIVERSE_DEBUG", default=True, cast=bool)
