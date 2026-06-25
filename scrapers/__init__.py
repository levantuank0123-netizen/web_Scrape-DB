"""Registry of all scraper adapters.

Hai loại adapter:
  - REGISTRY:      scraper chạy qua GPM + Playwright (core/runner.py)
  - HTTP_REGISTRY: scraper gọi API trực tiếp bằng requests (core/http_runner.py),
                   KHÔNG cần GPM/browser → nhanh + chính xác hơn.
"""
from scrapers.tolt import ToltScraper
from scrapers.getrewardful import RewardfulScraper
from scrapers.firstpromoter import FirstPromoterScraper
from scrapers.goaffpro import GoAffProScraper

# GPM + Playwright
REGISTRY = {
    "tolt": ToltScraper,
    "getrewardful": RewardfulScraper,
    "firstpromoter": FirstPromoterScraper,
}

# HTTP API thuần (không browser)
HTTP_REGISTRY = {
    "goaffpro": GoAffProScraper,
}


def get_scraper(platform: str):
    cls = REGISTRY.get(platform.lower())
    if not cls:
        raise ValueError(
            f"Chưa có adapter cho platform '{platform}'. "
            f"Hiện hỗ trợ: {sorted(REGISTRY)}"
        )
    return cls


def get_http_scraper(platform: str):
    cls = HTTP_REGISTRY.get(platform.lower())
    if not cls:
        raise ValueError(
            f"Chưa có HTTP adapter cho platform '{platform}'. "
            f"Hiện hỗ trợ: {sorted(HTTP_REGISTRY)}"
        )
    return cls


def is_http_platform(platform: str) -> bool:
    return platform.lower() in HTTP_REGISTRY
