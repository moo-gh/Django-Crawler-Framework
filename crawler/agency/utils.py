import logging
import re
from os import path
from typing import Optional, List
from urllib.parse import parse_qs

from django.utils import timezone
from django.core.exceptions import ValidationError
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.firefox.options import Options as FirefoxOptions

logger = logging.getLogger(__name__)

CODE = """
{0}
"""

# Define image file types as a tuple for immutability and faster lookups
IMAGE_FILE_TYPES: List[str] = ["jpeg", "jpg", "png", "bmp"]

DEFAULT_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

# Host SOCKS tunnel reached from the Docker network gateway.
# Keep in sync with docker-compose-pro.yml crawler_network subnet.
SOCKS_PROXY_HOST = "172.20.0.1"
SOCKS_PROXY_PORT = 1080
SOCKS_PROXY = f"{SOCKS_PROXY_HOST}:{SOCKS_PROXY_PORT}"

_PROXY_ERROR_MARKERS = (
    "proxyconnectfailure",
    "proxyresolvefailure",
    "proxy server that is refusing",
    "proxy server is refusing",
)

_NETERROR_HINTS = {
    "proxyConnectFailure": "the configured proxy refused the connection",
    "proxyResolveFailure": "the configured proxy hostname could not be resolved",
    "connectionFailure": "the site refused the connection",
    "dnsNotFound": "the site hostname could not be resolved",
    "netTimeout": "the connection timed out",
    "nssFailure2": "the SSL/TLS handshake failed",
    "netOffline": "the browser is offline",
    "malformedURI": "the URL is malformed",
}


class CrawlerNavigationError(Exception):
    """Browser failed to load a page. Message is meant for logs and Celery emails."""


def get_webdriver_error_text(exc: Exception) -> str:
    """Return Selenium's real error text (stored on .msg, not always on .args)."""
    return str(getattr(exc, "msg", None) or exc)


def _firefox_neterror_code(error_text: str) -> Optional[str]:
    match = re.search(r"about:neterror\?(\S+)", error_text)
    if not match:
        return None
    query = parse_qs(match.group(1))
    codes = query.get("e")
    if not codes:
        return None
    return codes[0]


def is_proxy_connection_error(exc: Exception) -> bool:
    error_text = get_webdriver_error_text(exc).lower()
    if any(marker in error_text for marker in _PROXY_ERROR_MARKERS):
        return True
    return _firefox_neterror_code(get_webdriver_error_text(exc)) in {
        "proxyConnectFailure",
        "proxyResolveFailure",
    }


def describe_navigation_error(
    exc: Exception, url: str, use_proxy: bool = False
) -> str:
    """Build a short, explicit reason for a Selenium navigation failure."""
    error_text = get_webdriver_error_text(exc)
    neterror_code = _firefox_neterror_code(error_text)

    if is_proxy_connection_error(exc):
        return (
            f"Proxy connection failed while loading {url}. "
            f"Firefox could not connect to SOCKS5 proxy {SOCKS_PROXY}. "
            "Check that the SSH SOCKS tunnel is running "
            "(ssh -D 0.0.0.0:1080 ...) and that UFW allows "
            f"172.20.0.0/16 to port {SOCKS_PROXY_PORT}."
        )

    proxy_note = f" via SOCKS5 proxy {SOCKS_PROXY}" if use_proxy else ""
    hint = _NETERROR_HINTS.get(neterror_code)
    if hint:
        return (
            f"Browser navigation failed{proxy_note} while loading {url}: {hint}."
        )
    return f"Browser navigation failed{proxy_note} while loading {url}: {error_text}"


def is_image(ext: str) -> bool:
    """
    Validate if the file extension is an allowed image type.

    Args:
        ext: File extension to validate

    Returns:
        bool: True if valid image extension

    Raises:
        ValidationError: If the extension is not in the allowed image types
    """
    if ext.lower() not in IMAGE_FILE_TYPES:
        raise ValidationError("unknown file format")
    return True


def report_image_path(_instance, filename: str) -> Optional[str]:
    """
    Generate a path for storing report images with a timestamp-based filename.

    Args:
        _instance: The model instance (unused but required by Django)
        filename: Original filename of the uploaded image

    Returns:
        str: Path where the image should be stored
        None: If the file is not a valid image
    """
    ext = filename.split(".")[-1].lower()
    if is_image(ext):
        return path.join(
            ".",
            "report",
            "images",
            f"{int(timezone.now().timestamp())}.{ext}",
        )
    return None


def get_browser_options(use_proxy: bool = False) -> FirefoxOptions:
    """
    Configure and return Firefox browser options for web scraping.

    Args:
        use_proxy: Whether to use a SOCKS proxy

    Returns:
        FirefoxOptions: Configured browser options
    """
    options = FirefoxOptions()
    options.set_capability("pageLoadStrategy", "eager")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--enable-automation")
    options.add_argument("--no-sandbox")

    if use_proxy:
        logger.info("Using proxy")

        # Establishing the SOCKS proxy
        # first you should create a socks connection in the host
        # like: ssh -D 0.0.0.0:1080 user-on-remote@remote-ip -p remote-port
        # second you should find the gateway ip for your container
        # like: docker network inspect bridge, look for gateway keyword (like 172.20.0.1)
        # third, be sure that you've allowed the port
        # like: ufw allow from 172.20.0.0/16 to any port 1080
        proxy = Proxy()
        proxy.proxy_type = ProxyType.MANUAL
        proxy.socks_proxy = SOCKS_PROXY
        proxy.socks_version = 5  # SOCKS5
        proxy.no_proxy = ""  # No exceptions
        options.proxy = proxy

    # Disable images
    options.set_preference("permissions.default.image", 2)

    # Disable JSON output formatting
    options.set_preference("devtools.jsonview.enabled", False)

    return options
