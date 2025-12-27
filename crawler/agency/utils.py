import logging
from os import path
from typing import Optional, List

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
        proxy.socks_proxy = "172.20.0.1:1080"  # Your SOCKS proxy
        proxy.socks_version = 5  # SOCKS5
        proxy.no_proxy = ""  # No exceptions
        options.proxy = proxy

    # Disable images
    options.set_preference("permissions.default.image", 2)

    # Disable JSON output formatting
    options.set_preference("devtools.jsonview.enabled", False)

    return options
