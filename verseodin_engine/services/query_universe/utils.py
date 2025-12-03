from typing import List, Optional
from urllib.parse import urlparse, urljoin
import re
from typing import Iterable


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """Normalize URL by adding https if no scheme is present."""
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def truncate_content(content: str, max_length: int = 10000) -> str:
    """Truncate content to max_length characters."""
    if len(content) <= max_length:
        return content
    return content[:max_length] + "... (truncated)"


def extract_brand_name_from_url(url: str) -> str:
    """
    Extract brand name from URL domain.
    Example: https://www.apple.com/about → "apple"
    """
    parsed = urlparse(url)
    domain = parsed.netloc
    # Remove www. and common TLDs
    domain = domain.replace('www.', '')
    domain = re.sub(r'\.(com|org|net|io|co|ai|app|dev).*$', '', domain)
    return domain.lower()


def brand_tokens_from_domain(url: str) -> List[str]:
    """
    Derive a set of brand tokens from the domain.
    Example: https://www.infinityapp.in -> ["infinityapp", "infinity"]
    """
    base = extract_brand_name_from_url(url)
    if not base:
        return []

    tokens = set()

    # Core label before first dot (e.g., infinityapp from infinityapp.in)
    core_label = base.split(".")[0]
    if core_label:
        tokens.add(core_label)
    tokens.add(base)

    # Common suffixes to strip to get the core brand token
    suffixes = ("app", "apps", "ai", "tech", "labs", "hq", "inc", "co", "io", "dev", "technology")
    for token in list(tokens):
        for suf in suffixes:
            if token.endswith(suf) and len(token) > len(suf) + 2:
                core = token[: -len(suf)]
                core = re.sub(r'[^a-zA-Z]+', '', core)
                if core:
                    tokens.add(core.lower())

    # Split on punctuation/hyphens/numbers to get component tokens
    parts = re.split(r'[^a-zA-Z]+', base)
    for p in parts:
        p = p.strip().lower()
        if p:
            tokens.add(p)

    # Filter out overly short tokens (e.g., "in") to reduce false positives
    return [t for t in tokens if t and len(t) >= 4]


def chunk_text(text: str, max_length: int = 2000, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks to preserve context without truncation.

    Args:
        text: Input string to chunk.
        max_length: Max characters per chunk.
        overlap: Characters of overlap between consecutive chunks.

    Returns:
        List of text chunks.
    """
    if not text:
        return []

    chunks: List[str] = []
    start = 0
    end = max_length
    text_len = len(text)

    while start < text_len:
        chunks.append(text[start:end])
        if end >= text_len:
            break
        start = max(end - overlap, start + 1)
        end = start + max_length

    return chunks


def get_url_path(url: str) -> str:
    """
    Get the path portion of a URL.
    Example: https://example.com/about/team → "/about/team"
    """
    parsed = urlparse(url)
    return parsed.path.lower()


def matches_priority_pattern(url: str, patterns: List[str]) -> bool:
    """
    Check if URL path matches any of the given patterns.
    
    Args:
        url: The URL to check
        patterns: List of path patterns like ["/about", "/about-us"]
    
    Returns:
        True if URL matches any pattern
    """
    path = get_url_path(url)
    
    for pattern in patterns:
        pattern_lower = pattern.lower()

        if pattern in ("/", ""):
            return path in ("/", "")

        
        # Exact match
        if path == pattern_lower:
            return True
        
        # Starts with pattern (e.g., /blog matches /blog/post-1)
        if path.startswith(pattern_lower + "/") or path.startswith(pattern_lower + "?"):
            return True
        
        # Pattern in path
        if pattern_lower in path:
            return True
    
    return False


def is_brand_blog(url: str, brand_tokens: List[str], title: Optional[str] = None) -> bool:
    """
    Check if a blog URL mentions the brand name.
    
    Args:
        url: The blog URL
        brand_tokens: Candidate brand tokens to look for
        title: Optional page title to check
    
    Returns:
        True if URL or title contains brand name
    """
    # Check URL path
    path = get_url_path(url)
    for token in brand_tokens:
        if token and token in path:
            return True
    
    # Check title if provided
    if title:
        lower = title.lower()
        for token in brand_tokens:
            if token and token in lower:
                return True
    
    return False


def select_urls_to_crawl(
    urls: List[str], 
    max_urls: int,
    homepage_url: Optional[str] = None,
    priority_patterns: Optional[List[tuple]] = None,
) -> List[str]:
    """
    Smart URL selection with priority-based ordering.
    
    Priority order:
    1. Homepage
    2. About pages
    3. FAQ pages
    4. Sitemap
    5. Product/Service pages
    6. Blog index pages
    7. Brand-specific blog posts (containing brand name)
    8. Other URLs
    
    Args:
        urls: List of URLs to select from
        max_urls: Maximum number of URLs to return
        homepage_url: The homepage URL (to extract brand name)
        priority_patterns: List of (category, patterns) tuples
    
    Returns:
        List of selected URLs in priority order
    """
    if not urls:
        return []
    
    # If no priority patterns provided, use simple selection
    if not priority_patterns:
        return sorted(urls)[:max_urls]
    
    # Extract brand tokens from homepage if provided
    brand_tokens = brand_tokens_from_domain(homepage_url) if homepage_url else []
    
    # Categorize URLs by priority
    categorized = {
        "homepage": [],
        "about": [],
        "faq": [],
        "sitemap": [],
        "product": [],
        "brand_blog": [],
        "blog": [],
        "other": []
    }
    
    for url in urls:
        # Strip whitespace from URL
        url = url.strip()
        if not url:
            continue

        placed = False
        path = get_url_path(url)

        # Use global brand tokens or fall back to tokens from this URL's domain
        tokens_for_url = brand_tokens or brand_tokens_from_domain(url)

        # Fast-path: brand blog detection before category checks
        if tokens_for_url and "/blog" in path and is_brand_blog(url, tokens_for_url):
            categorized["brand_blog"].append(url)
            placed = True
        
        # Check each priority category (with special handling for blog vs brand_blog)
        for category, patterns in priority_patterns:
            if placed:
                break
            if not matches_priority_pattern(url, patterns):
                continue

            if category == "blog":
                # Skip plain blog index pages (e.g., /blog) to focus on brand-specific slugs
                if path.rstrip("/") in ("/blog", "blog"):
                    placed = True
                    break
                if tokens_for_url and is_brand_blog(url, tokens_for_url):
                    categorized["brand_blog"].append(url)
                else:
                    categorized["blog"].append(url)
            else:
                categorized[category].append(url)

            placed = True
            break
        
        # If it's a blog and not yet placed, check if it's a brand blog
        if not placed and brand_tokens:
            path = get_url_path(url)
            if any(blog_pattern in path for _, blog_patterns in priority_patterns 
                   if _ == "blog" for blog_pattern in blog_patterns):
                if is_brand_blog(url, brand_tokens):
                    categorized["brand_blog"].append(url)
                    placed = True
        
        # Place in "other" if still not categorized
        if not placed:
            categorized["other"].append(url)
    
    # Build final list in priority order
    selected = []
    # Adjusted priority: homepage -> about -> faq -> sitemap -> brand blogs -> products -> other blogs -> other
    priority_order = ["homepage", "about", "faq", "product", "brand_blog", "sitemap", "blog", "other"]
    
    for category in priority_order:
        if len(selected) >= max_urls:
            break
        
        # Add URLs from this category
        remaining = max_urls - len(selected)
        category_urls = sorted(categorized[category])[:remaining]
        selected.extend(category_urls)
    print("HOMEPAGE")
    print(categorized["homepage"])
    print("ABOUT")
    print(categorized["about"])
    print("FAQS")
    print(categorized["faq"])
    print("PRODUCT")
    print(categorized["product"])
    print("BRAND BLOGS")
    print(categorized["brand_blog"])
    print("SELECTED")
    print(selected[:max_urls])
    return selected[:max_urls]
