from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class FindOptions:
    """Configuration options for URL finding."""

    # Core crawling parameters
    max_depth: Optional[int] = 12
    max_urls: Optional[int] = 50000
    batch_size: Optional[int] = 100

    # HTTP request settings
    request_timeout: Optional[int] = 30
    request_delay: Optional[float] = 0.1
    batch_delay: Optional[float] = 1.0
    # DO NOT INCREASE max_concurrent_requests - THIS WILL BREAK REQUESTS
    max_concurrent_requests: Optional[int] = 100

    # User agent
    user_agent: Optional[str] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    # Required proxy field with default None
    proxy: str = None  # Must be provided, but defaults to None

    # Additional options
    headers: Optional[Dict[str, str]] = None
    excluded_extensions: Optional[List[str]] = None
    require_same_domain: Optional[bool] = None


@dataclass
class FindDoc:
    input_url: str
    homepage_url: str
    domain: str
    urls: Set[str]
    total_found: int
    max_depth_reached: int
    successful_crawls: int
    failed_crawls: int
    processing_time: float
    meta: Dict[str, Any] = field(default_factory=dict)
