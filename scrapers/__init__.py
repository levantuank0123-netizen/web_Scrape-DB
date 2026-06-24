"""Registry of all scraper adapters."""
from scrapers.tolt import ToltScraper
from scrapers.getrewardful import RewardfulScraper
from scrapers.firstpromoter import FirstPromoterScraper

REGISTRY = {
    "tolt": ToltScraper,
    "getrewardful": RewardfulScraper,
    "firstpromoter": FirstPromoterScraper,
}


def get_scraper(platform: str):
    cls = REGISTRY.get(platform.lower())
    if not cls:
        raise ValueError(
            f"Chưa có adapter cho platform '{platform}'. "
            f"Hiện hỗ trợ: {sorted(REGISTRY)}"
        )
    return cls
