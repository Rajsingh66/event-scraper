"""
deduplication.py — Three-Layer Deduplication Engine

Layer 1: Exact source_id match (same event, same platform)
Layer 2: Content hash match (same event, different platform)
Layer 3: Fuzzy title match (near-duplicate on same date+city)
"""

import hashlib
import re
from rapidfuzz import fuzz


def normalize_text(text: str) -> str:
    """Lowercase, strip extra spaces, remove special chars."""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text


def normalize_date(date_str: str) -> str:
    """Extract just YYYY-MM-DD from any datetime string."""
    if not date_str:
        return ""
    return str(date_str).strip()[:10]


def compute_content_hash(title: str, start_date: str, city: str) -> str:
    """
    SHA-256 hash of normalized title + date + city.
    This fingerprints the real-world event, not the listing.
    Same event on Eventbrite and Meetup → same hash.
    """
    fingerprint = "|".join([
        normalize_text(title),
        normalize_date(start_date),
        normalize_text(city)
    ])
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def is_duplicate(
    event: dict,
    existing_source_ids: set,
    existing_hashes: set,
    existing_events: list,
    fuzzy_threshold: int = 85
) -> tuple[bool, str]:
    """
    Check if event is a duplicate using 3 layers.

    Returns:
        (is_duplicate: bool, reason: str)

    Reason values:
        "exact_source_id"  — same platform, same event ID
        "content_hash"     — same event on different platform
        "fuzzy_match_XX%"  — near-duplicate title on same date+city
        ""                 — not a duplicate
    """

    # ── Layer 1: Exact source ID ─────────────────────────────
    source_id = str(event.get("source_id", "")).strip()
    if source_id and source_id in existing_source_ids:
        return True, "exact_source_id"

    # ── Layer 2: Content Hash ────────────────────────────────
    content_hash = compute_content_hash(
        event.get("title", ""),
        event.get("start_date", ""),
        event.get("city", "")
    )
    if content_hash in existing_hashes:
        return True, "content_hash"

    # ── Layer 3: Fuzzy Title Match ───────────────────────────
    new_title_norm = normalize_text(event.get("title", ""))
    new_date_norm = normalize_date(event.get("start_date", ""))
    new_city_norm = normalize_text(event.get("city", ""))

    for existing in existing_events:
        # Only compare events on same date AND city (performance gate)
        same_date = normalize_date(existing.get("start_date", "")) == new_date_norm
        same_city = normalize_text(existing.get("city", "")) == new_city_norm

        if same_date and same_city and new_date_norm:
            existing_title_norm = normalize_text(existing.get("title", ""))
            similarity = fuzz.token_sort_ratio(new_title_norm, existing_title_norm)

            if similarity >= fuzzy_threshold:
                return True, f"fuzzy_match_{similarity}pct"

    return False, ""


def prepare_event_row(event: dict) -> list:
    """
    Convert event dict to a sheet row in the correct column order.
    Matches EVENTS_HEADERS in sheets.py.
    """
    from sheets import EVENTS_HEADERS
    from datetime import datetime

    content_hash = compute_content_hash(
        event.get("title", ""),
        event.get("start_date", ""),
        event.get("city", "")
    )

    event_data = {
        "content_hash": content_hash,
        "title": event.get("title", ""),
        "start_date": event.get("start_date", ""),
        "end_date": event.get("end_date", ""),
        "city": event.get("city", ""),
        "country": event.get("country", "India"),
        "platform": event.get("platform", ""),
        "source_id": str(event.get("source_id", "")),
        "url": event.get("url", ""),
        "category": event.get("category", ""),
        "price": event.get("price", "Free"),
        "is_free": "TRUE" if event.get("is_free", True) else "FALSE",
        "organizer": event.get("organizer", ""),
        "description": str(event.get("description", ""))[:500],  # cap at 500 chars
        "attendee_count": event.get("attendee_count", ""),
        "image_url": event.get("image_url", ""),
        "scraped_at": datetime.now().isoformat(),
        "is_active": "TRUE"
    }

    return [event_data.get(h, "") for h in EVENTS_HEADERS]
