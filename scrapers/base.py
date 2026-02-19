"""
scrapers/base.py — Base Scraper Interface
All platform scrapers inherit from this.
"""

import httpx
import random
import asyncio
from abc import ABC, abstractmethod
from fake_useragent import UserAgent


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


class BaseScraper(ABC):
    """
    Every scraper must implement fetch_events().
    It returns a list of normalized event dicts.
    """

    PLATFORM_NAME: str = "unknown"

    def __init__(self):
        self.session = None

    def get_headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }

    async def polite_delay(self, min_sec: float = 1.5, max_sec: float = 3.5):
        """Random delay between requests — be polite to servers."""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    @abstractmethod
    async def fetch_events(self, city: str, category: str = "") -> list[dict]:
        """
        Scrape events for given city and category.
        Must return list of normalized event dicts.
        """
        pass

    def normalize_event(self, raw: dict) -> dict:
        """
        Subclasses call this to ensure every event has required fields.
        Fill in defaults for missing fields.
        """
        return {
            "title": raw.get("title", "Untitled Event"),
            "description": raw.get("description", ""),
            "start_date": raw.get("start_date", ""),
            "end_date": raw.get("end_date", ""),
            "city": raw.get("city", ""),
            "country": raw.get("country", "India"),
            "platform": self.PLATFORM_NAME,
            "source_id": str(raw.get("source_id", "")),
            "url": raw.get("url", ""),
            "category": raw.get("category", ""),
            "price": raw.get("price", "Free"),
            "is_free": raw.get("is_free", True),
            "organizer": raw.get("organizer", ""),
            "attendee_count": raw.get("attendee_count", ""),
            "image_url": raw.get("image_url", ""),
        }
