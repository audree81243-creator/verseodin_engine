from typing import Optional
from urllib.parse import urlparse

from decouple import config


def get_proxy_from_env() -> Optional[str]:
    """Get proxy URL from environment variables or raise error if not found"""
    # Get proxy credentials from environment using decouple
    proxy_server = config("PROXY_SERVER", default=None)
    proxy_username = config("PROXY_USER", default=None) or config("PROXY_USERNAME", default=None)
    proxy_password = config("PROXY_PASSWORD", default=None)
    proxy_url = config("PROXY_URL", default=None)

    # If we have a complete proxy URL, use it directly
    if proxy_url and proxy_url != "your_proxy_url_here":
        return proxy_url

    # Otherwise construct from individual components
    if (
        proxy_server
        and proxy_username
        and proxy_password
        and "your_proxy" not in proxy_server.lower()
        and "your_proxy" not in proxy_username.lower()
        and "your_proxy" not in proxy_password.lower()
    ):
        # Construct proxy URL: http://username:password@server:port
        server_clean = proxy_server.replace("http://", "").replace("https://", "")
        return f"http://{proxy_username}:{proxy_password}@{server_clean}"

    # No valid proxy configuration found
    return None


def extract_homepage_from_url(url: str) -> str:
    """Extract homepage URL from any URL"""
    parsed = urlparse(url if url.startswith(("http://", "https://")) else f"https://{url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def validate_input_url(url: str) -> str:
    """Validate and normalize input URL"""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def get_domain_from_url(url: str) -> str:
    """Extract domain from URL"""
    return urlparse(url).netloc
