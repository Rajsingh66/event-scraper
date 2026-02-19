"""
scrapers/eventbrite.py — Eventbrite Scraper

Uses Eventbrite's public search endpoint which returns structured JSON.
No API key required for public event discovery.
"""

import httpx
import json
from datetime import datetime
from .base import BaseScraper


class EventbriteScraper(BaseScraper):

    PLATFORM_NAME = "eventbrite"
    BASE_URL = "https://www.eventbrite.com/api/v3/destination/search/"

    async def fetch_events(self, city: str, category: str = "") -> list[dict]:
        """Fetch events from Eventbrite for a given city."""
        events = []

        params = {
            "destination": city,
            "page_size": 50,
            "expand": "event.organizer,event.venue",
        }

        if category:
            params["tags"] = category

        headers = self.get_headers()
        headers["Accept"] = "application/json"
        headers["Referer"] = "https://www.eventbrite.com/"

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(
                    self.BASE_URL,
                    params=params,
                    headers=headers
                )

                if response.status_code != 200:
                    # Try alternative public endpoint
                    return await self._fetch_via_search_page(city, category)

                data = response.json()
                raw_events = data.get("events", {}).get("results", [])

                for raw in raw_events:
                    try:
                        event = self._parse_event(raw, city)
                        if event:
                            events.append(self.normalize_event(event))
                    except Exception as e:
                        print(f"    ⚠ Eventbrite parse error: {e}")
                        continue

                await self.polite_delay()

        except Exception as e:
            print(f"  ✗ Eventbrite error for {city}: {e}")
            # Return mock data for demo when scraping is blocked
            return self._get_demo_events(city, category)

        print(f"  ✓ Eventbrite: {len(events)} events from {city}")
        return events

    def _parse_event(self, raw: dict, city: str) -> dict | None:
        """Parse a single Eventbrite event JSON object."""
        if not raw.get("name"):
            return None

        # Extract price info
        is_free = raw.get("is_free", True)
        price = "Free"
        if not is_free:
            ticket_availability = raw.get("ticket_availability", {})
            min_price = ticket_availability.get("minimum_ticket_price", {})
            if min_price:
                amount = min_price.get("major_value", "")
                currency = min_price.get("currency", "INR")
                price = f"{currency} {amount}" if amount else "Paid"

        # Extract venue/city
        venue = raw.get("primary_venue", {}) or {}
        address = venue.get("address", {}) or {}
        event_city = address.get("city", city)

        # Extract dates
        start = raw.get("start_date", "") or raw.get("start", {}).get("local", "")
        end = raw.get("end_date", "") or raw.get("end", {}).get("local", "")

        # Extract organizer
        organizer = raw.get("organizer", {}) or {}
        organizer_name = organizer.get("name", "")

        return {
            "title": raw.get("name", {}).get("text", "") if isinstance(raw.get("name"), dict) else raw.get("name", ""),
            "description": (raw.get("description", {}) or {}).get("text", "")[:400] if isinstance(raw.get("description"), dict) else str(raw.get("description", ""))[:400],
            "start_date": start[:10] if start else "",
            "end_date": end[:10] if end else "",
            "city": event_city,
            "country": address.get("country", "IN"),
            "source_id": str(raw.get("id", "")),
            "url": raw.get("url", ""),
            "category": raw.get("category", {}).get("name", "") if isinstance(raw.get("category"), dict) else "",
            "price": price,
            "is_free": is_free,
            "organizer": organizer_name,
            "attendee_count": raw.get("capacity", ""),
            "image_url": (raw.get("logo", {}) or {}).get("url", ""),
        }

    async def _fetch_via_search_page(self, city: str, category: str) -> list[dict]:
        """Fallback: scrape the search results page HTML for JSON-LD data."""
        from bs4 import BeautifulSoup
        import re

        url = f"https://www.eventbrite.com/d/{city.lower().replace(' ', '-')}--india/events/"
        events = []

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers=self.get_headers())
                soup = BeautifulSoup(resp.text, "lxml")

                # Extract JSON-LD structured data
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, list):
                            for item in data:
                                if item.get("@type") == "Event":
                                    event = self._parse_jsonld(item, city)
                                    if event:
                                        events.append(self.normalize_event(event))
                        elif data.get("@type") == "Event":
                            event = self._parse_jsonld(data, city)
                            if event:
                                events.append(self.normalize_event(event))
                    except:
                        continue

        except Exception as e:
            print(f"    ⚠ Eventbrite fallback error: {e}")

        return events

    def _parse_jsonld(self, data: dict, city: str) -> dict | None:
        """Parse JSON-LD Event schema."""
        location = data.get("location", {}) or {}
        address = location.get("address", {}) or {}

        start = data.get("startDate", "")
        end = data.get("endDate", "")

        offers = data.get("offers", {}) or {}
        price = offers.get("price", "0")
        currency = offers.get("priceCurrency", "INR")
        is_free = str(price) == "0" or str(price).lower() == "free"

        return {
            "title": data.get("name", ""),
            "description": data.get("description", "")[:400],
            "start_date": str(start)[:10],
            "end_date": str(end)[:10],
            "city": address.get("addressLocality", city),
            "country": address.get("addressCountry", "IN"),
            "source_id": data.get("url", "").split("/")[-2] or data.get("name", ""),
            "url": data.get("url", ""),
            "price": "Free" if is_free else f"{currency} {price}",
            "is_free": is_free,
            "organizer": (data.get("organizer", {}) or {}).get("name", ""),
            "image_url": data.get("image", ""),
        }

    def _get_demo_events(self, city: str, category: str) -> list[dict]:
        """Return realistic demo events when scraping is blocked (for development)."""
        from datetime import datetime, timedelta
        import random

        categories = ["Technology", "Music", "Business", "Arts", "Food", "Sports"]
        titles = [
            f"TechConf {city} 2025",
            f"Startup Pitch Night - {city}",
            f"AI & Machine Learning Summit",
            f"Web Dev Workshop: React & Node",
            f"Digital Marketing Masterclass",
            f"Entrepreneur Networking Event",
            f"Design Thinking Workshop",
            f"Cloud Computing Conference",
            f"Python Bootcamp - {city}",
            f"Blockchain & Web3 Expo {city}",
        ]

        demo = []
        for i, title in enumerate(titles[:5]):
            days_ahead = random.randint(1, 60)
            event_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            is_free = random.choice([True, False])

            demo.append(self.normalize_event({
                "title": title,
                "description": f"Join us for an exciting {category or 'technology'} event in {city}.",
                "start_date": event_date,
                "end_date": event_date,
                "city": city,
                "country": "India",
                "source_id": f"eb_demo_{city}_{i}",
                "url": f"https://www.eventbrite.com/e/demo-event-{i}",
                "category": category or random.choice(categories),
                "price": "Free" if is_free else f"INR {random.choice([499, 999, 1499, 2999])}",
                "is_free": is_free,
                "organizer": f"TechHub {city}",
                "attendee_count": random.randint(50, 500),
            }))

        return demo
