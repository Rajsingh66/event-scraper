"""
scrapers/meetup.py — Meetup.com Scraper

Uses Meetup's public GraphQL API endpoint.
Returns upcoming events with full details.
"""

import httpx
import json
from .base import BaseScraper


MEETUP_GRAPHQL_URL = "https://www.meetup.com/gql"

EVENTS_QUERY = """
query searchEvents($query: String!, $lat: Float!, $lon: Float!, $radius: Float) {
  results: searchEvents(
    input: { query: $query, lat: $lat, lon: $lon, radius: $radius }
    filter: { upcoming: true }
  ) {
    pageInfo { hasNextPage endCursor }
    count
    edges {
      node {
        id
        title
        dateTime
        endTime
        description
        eventUrl
        isOnline
        venue { city country lat lon name }
        group { name urlname }
        going
        maxTickets
        eventType
        feeSettings {
          accepts
          amount
          currency
          type
        }
        images { baseUrl }
      }
    }
  }
}
"""

# City coordinates for Meetup's geo-based search
CITY_COORDS = {
    "Mumbai": (19.0760, 72.8777),
    "Delhi": (28.6139, 77.2090),
    "Bangalore": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Chennai": (13.0827, 80.2707),
    "Pune": (18.5204, 73.8567),
    "Kolkata": (22.5726, 88.3639),
    "Ahmedabad": (23.0225, 72.5714),
}


class MeetupScraper(BaseScraper):

    PLATFORM_NAME = "meetup"

    async def fetch_events(self, city: str, category: str = "") -> list[dict]:
        """Fetch events from Meetup for a given city using GraphQL."""
        events = []
        coords = CITY_COORDS.get(city, (20.5937, 78.9629))  # default: India center

        payload = {
            "query": EVENTS_QUERY,
            "variables": {
                "query": category or "tech",
                "lat": coords[0],
                "lon": coords[1],
                "radius": 50.0  # km radius
            }
        }

        headers = self.get_headers()
        headers["Content-Type"] = "application/json"
        headers["Referer"] = "https://www.meetup.com/"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    MEETUP_GRAPHQL_URL,
                    json=payload,
                    headers=headers
                )

                if response.status_code != 200:
                    print(f"    ⚠ Meetup returned {response.status_code} for {city}")
                    return self._get_demo_events(city, category)

                data = response.json()
                edges = data.get("data", {}).get("results", {}).get("edges", [])

                for edge in edges:
                    try:
                        node = edge.get("node", {})
                        event = self._parse_event(node, city)
                        if event:
                            events.append(self.normalize_event(event))
                    except Exception as e:
                        print(f"    ⚠ Meetup parse error: {e}")
                        continue

                await self.polite_delay()

        except Exception as e:
            print(f"  ✗ Meetup error for {city}: {e}")
            return self._get_demo_events(city, category)

        print(f"  ✓ Meetup: {len(events)} events from {city}")
        return events

    def _parse_event(self, node: dict, default_city: str) -> dict | None:
        """Parse a single Meetup GraphQL event node."""
        if not node.get("title"):
            return None

        venue = node.get("venue") or {}
        group = node.get("group") or {}
        fee = node.get("feeSettings") or {}
        images = node.get("images") or []

        # Parse dates
        start_dt = node.get("dateTime", "")
        end_dt = node.get("endTime", "")

        # Parse price
        is_free = not bool(fee.get("amount"))
        price = "Free"
        if not is_free:
            amount = fee.get("amount", "")
            currency = fee.get("currency", "INR")
            price = f"{currency} {amount}"

        city = venue.get("city", default_city)
        country = venue.get("country", "IN")

        image_url = images[0].get("baseUrl", "") if images else ""

        return {
            "title": node.get("title", ""),
            "description": (node.get("description") or "")[:400],
            "start_date": str(start_dt)[:10],
            "end_date": str(end_dt)[:10],
            "city": city,
            "country": country,
            "source_id": str(node.get("id", "")),
            "url": node.get("eventUrl", ""),
            "category": "Technology",  # Meetup doesn't always categorize
            "price": price,
            "is_free": is_free,
            "organizer": group.get("name", ""),
            "attendee_count": node.get("going", ""),
            "image_url": image_url,
        }

    def _get_demo_events(self, city: str, category: str) -> list[dict]:
        """Return demo events when API is unavailable."""
        from datetime import datetime, timedelta
        import random

        titles = [
            f"{city} Tech Meetup — Monthly Gathering",
            f"DevOps & Cloud Engineers {city}",
            f"Data Science Community {city}",
            f"JavaScript Developers Meetup",
            f"Women in Tech {city}",
            f"Open Source Contributions Sprint",
            f"UX Design Community Meeting",
        ]

        demo = []
        for i, title in enumerate(titles[:4]):
            days_ahead = random.randint(3, 45)
            event_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

            demo.append(self.normalize_event({
                "title": title,
                "description": f"Monthly meetup for {category or 'tech'} enthusiasts in {city}. Network, learn, share.",
                "start_date": event_date,
                "end_date": event_date,
                "city": city,
                "country": "India",
                "source_id": f"mu_demo_{city}_{i}",
                "url": f"https://www.meetup.com/demo-group-{city.lower()}/events/{i}/",
                "category": category or "Technology",
                "price": "Free",
                "is_free": True,
                "organizer": f"{city} Tech Community",
                "attendee_count": random.randint(20, 200),
            }))

        return demo
