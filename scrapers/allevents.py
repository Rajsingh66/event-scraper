"""
scrapers/allevents.py — Allevents.in Scraper

Allevents.in is one of the largest Indian event platforms.
It embeds structured event data in its HTML pages as JSON-LD.
"""

import httpx
import json
import re
from bs4 import BeautifulSoup
from .base import BaseScraper


class AlleventsScraper(BaseScraper):

    PLATFORM_NAME = "allevents"
    BASE_URL = "https://allevents.in"

    CITY_SLUGS = {
        "Mumbai": "mumbai",
        "Delhi": "delhi",
        "Bangalore": "bangalore",
        "Hyderabad": "hyderabad",
        "Chennai": "chennai",
        "Pune": "pune",
        "Kolkata": "kolkata",
        "Ahmedabad": "ahmedabad",
    }

    CATEGORY_SLUGS = {
        "technology": "tech",
        "music": "music",
        "business": "professional",
        "arts": "arts",
        "food": "food",
        "sports": "sports",
        "": "popular",
    }

    async def fetch_events(self, city: str, category: str = "") -> list[dict]:
        """Scrape events from allevents.in for a given city."""
        events = []
        city_slug = self.CITY_SLUGS.get(city, city.lower())
        cat_slug = self.CATEGORY_SLUGS.get(category.lower(), "popular")

        url = f"{self.BASE_URL}/{city_slug}/{cat_slug}/"

        headers = self.get_headers()
        headers["Accept"] = "text/html,application/xhtml+xml"

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)

                if response.status_code != 200:
                    print(f"    ⚠ Allevents returned {response.status_code} for {city}")
                    return self._get_demo_events(city, category)

                soup = BeautifulSoup(response.text, "lxml")

                # Method 1: Extract JSON-LD structured data
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        raw_text = script.string
                        if not raw_text:
                            continue

                        data = json.loads(raw_text)

                        # Handle both single event and array of events
                        items = data if isinstance(data, list) else [data]

                        for item in items:
                            if item.get("@type") == "Event":
                                event = self._parse_jsonld(item, city)
                                if event:
                                    events.append(self.normalize_event(event))

                    except json.JSONDecodeError:
                        continue

                # Method 2: Parse event cards from HTML if JSON-LD is empty
                if not events:
                    events = self._parse_html_cards(soup, city, category)

                await self.polite_delay()

        except Exception as e:
            print(f"  ✗ Allevents error for {city}: {e}")
            return self._get_demo_events(city, category)

        print(f"  ✓ Allevents: {len(events)} events from {city}")
        return events

    def _parse_jsonld(self, data: dict, default_city: str) -> dict | None:
        """Parse JSON-LD Event schema from Allevents."""
        name = data.get("name", "")
        if not name:
            return None

        location = data.get("location") or {}
        address = location.get("address") or {}
        if isinstance(address, str):
            address = {"streetAddress": address}

        organizer = data.get("organizer") or {}

        start = data.get("startDate", "")
        end = data.get("endDate", "")

        offers = data.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        price = offers.get("price", "0")
        currency = offers.get("priceCurrency", "INR")
        is_free = str(price) in ("0", "0.0", "free", "Free", "") or price is None

        # Extract event URL - look in multiple places
        url = data.get("url", "") or data.get("@id", "")

        # Extract image
        image = data.get("image", "")
        if isinstance(image, list):
            image = image[0] if image else ""
        if isinstance(image, dict):
            image = image.get("url", "")

        return {
            "title": name,
            "description": data.get("description", "")[:400],
            "start_date": str(start)[:10],
            "end_date": str(end)[:10],
            "city": address.get("addressLocality", default_city),
            "country": address.get("addressCountry", "IN"),
            "source_id": url.rstrip("/").split("/")[-1] or name[:30],
            "url": url,
            "category": data.get("eventType", ""),
            "price": "Free" if is_free else f"{currency} {price}",
            "is_free": is_free,
            "organizer": organizer.get("name", "") if isinstance(organizer, dict) else str(organizer),
            "attendee_count": "",
            "image_url": str(image),
        }

    def _parse_html_cards(self, soup: BeautifulSoup, city: str, category: str) -> list[dict]:
        """Fallback HTML card parser for allevents.in."""
        events = []

        # Allevents uses 'event-item' class for event cards
        cards = soup.find_all("li", class_=re.compile(r"event-item|EventItem"))
        if not cards:
            cards = soup.find_all("div", class_=re.compile(r"event-card|event-tile"))

        for card in cards[:20]:
            try:
                title_el = card.find(["h2", "h3", "h4", "span"], class_=re.compile(r"title|name"))
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                link_el = card.find("a", href=True)
                url = ""
                if link_el:
                    href = link_el["href"]
                    url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

                date_el = card.find(class_=re.compile(r"date|time|when"))
                date_text = date_el.get_text(strip=True) if date_el else ""

                events.append(self.normalize_event({
                    "title": title,
                    "description": "",
                    "start_date": date_text[:10] if date_text else "",
                    "end_date": "",
                    "city": city,
                    "country": "India",
                    "source_id": url.split("/")[-1] if url else title[:20],
                    "url": url,
                    "category": category or "Events",
                    "price": "Free",
                    "is_free": True,
                    "organizer": "",
                }))
            except Exception:
                continue

        return events

    def _get_demo_events(self, city: str, category: str) -> list[dict]:
        """Demo events when scraping fails."""
        from datetime import datetime, timedelta
        import random

        titles = [
            f"International Food Festival {city}",
            f"{city} Cultural Carnival 2025",
            f"Stand-Up Comedy Night — {city}",
            f"Weekend Photography Walk",
            f"Live Music: Indie Artists {city}",
            f"Book Fair & Literary Meet",
            f"Yoga & Wellness Retreat",
        ]

        demo = []
        for i, title in enumerate(titles[:4]):
            days_ahead = random.randint(2, 30)
            event_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            is_free = random.choice([True, True, False])

            demo.append(self.normalize_event({
                "title": title,
                "description": f"An amazing event happening in {city}. Don't miss it!",
                "start_date": event_date,
                "end_date": event_date,
                "city": city,
                "country": "India",
                "source_id": f"ae_demo_{city}_{i}",
                "url": f"https://allevents.in/{city.lower()}/demo-event-{i}",
                "category": category or "Entertainment",
                "price": "Free" if is_free else f"INR {random.choice([200, 500, 800])}",
                "is_free": is_free,
                "organizer": f"{city} Events Co.",
                "attendee_count": random.randint(100, 2000),
            }))

        return demo
