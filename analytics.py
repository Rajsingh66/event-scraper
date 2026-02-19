"""
analytics.py — Compute stats from events list for Google Sheets + Dashboard
"""

from collections import Counter
from datetime import datetime


def compute_stats(events: list[dict]) -> dict:
    """
    Given all events (list of dicts from sheet), compute all analytics.
    Returns a flat dict of metric_name → value.
    """
    if not events:
        return {"total_events": 0}

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # Basic counts
    total = len(events)
    active = sum(1 for e in events if str(e.get("is_active", "")).upper() == "TRUE")
    free_count = sum(1 for e in events if str(e.get("is_free", "")).upper() == "TRUE")
    paid_count = total - free_count

    # Platform counts
    platforms = Counter(e.get("platform", "unknown") for e in events)

    # City counts
    cities = Counter(e.get("city", "unknown") for e in events if e.get("city"))
    top_cities = cities.most_common(10)

    # Category counts
    categories = Counter(e.get("category", "uncategorized") for e in events if e.get("category"))
    top_categories = categories.most_common(10)

    # Events added today
    added_today = sum(
        1 for e in events
        if str(e.get("scraped_at", "")).startswith(today_str)
    )

    # Events this week
    week_start = now.strftime("%Y-%m-")
    added_this_week = sum(
        1 for e in events
        if str(e.get("scraped_at", ""))[:7] == today_str[:7]
    )

    # Upcoming events (start_date >= today)
    upcoming = sum(
        1 for e in events
        if str(e.get("start_date", "")) >= today_str
        and str(e.get("is_active", "")).upper() == "TRUE"
    )

    stats = {
        "total_events": total,
        "active_events": active,
        "upcoming_events": upcoming,
        "free_events": free_count,
        "paid_events": paid_count,
        "total_platforms": len(platforms),
        "added_today": added_today,
        "added_this_month": added_this_week,
        "last_updated": now.isoformat(),
    }

    # Platform breakdown
    for platform, count in platforms.items():
        stats[f"platform_{platform}"] = count

    # Top cities
    for city, count in top_cities:
        stats[f"city_{city}"] = count

    # Top categories
    for cat, count in top_categories:
        clean_cat = cat.replace(" ", "_").lower()[:30]
        stats[f"category_{clean_cat}"] = count

    return stats


def compute_dashboard_data(events: list[dict]) -> dict:
    """
    Compute rich analytics data specifically for the dashboard UI.
    Returns structured data (lists, dicts) rather than flat metrics.
    """
    if not events:
        return {}

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # ── Platform breakdown ───────────────────────────────────
    platforms = Counter(e.get("platform", "unknown") for e in events)
    platform_data = [
        {"name": p.title(), "count": c, "platform": p}
        for p, c in platforms.most_common()
    ]

    # ── Top cities ───────────────────────────────────────────
    cities = Counter(e.get("city", "") for e in events if e.get("city"))
    city_data = [
        {"city": city, "count": count}
        for city, count in cities.most_common(10)
    ]

    # ── Category breakdown ───────────────────────────────────
    categories = Counter(
        e.get("category", "Other") or "Other"
        for e in events
    )
    category_data = [
        {"category": cat[:25], "count": count}
        for cat, count in categories.most_common(8)
    ]

    # ── Daily scraping timeline (last 30 days) ───────────────
    from collections import defaultdict
    daily_counts = defaultdict(int)

    for e in events:
        scraped = str(e.get("scraped_at", ""))
        if scraped:
            day = scraped[:10]
            daily_counts[day] += 1

    # Fill in last 30 days
    from datetime import timedelta
    timeline = []
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        timeline.append({"date": day, "count": daily_counts.get(day, 0)})

    # ── Free vs Paid ─────────────────────────────────────────
    free_count = sum(1 for e in events if str(e.get("is_free", "")).upper() == "TRUE")
    paid_count = len(events) - free_count

    # ── Upcoming events ──────────────────────────────────────
    upcoming = sorted(
        [e for e in events if str(e.get("start_date", "")) >= today_str],
        key=lambda x: x.get("start_date", "")
    )[:20]

    # ── Recent additions ─────────────────────────────────────
    recent = sorted(
        events,
        key=lambda x: str(x.get("scraped_at", "")),
        reverse=True
    )[:10]

    # ── KPI Numbers ──────────────────────────────────────────
    added_today = sum(
        1 for e in events
        if str(e.get("scraped_at", "")).startswith(today_str)
    )

    return {
        "kpis": {
            "total_events": len(events),
            "active_events": sum(1 for e in events if str(e.get("is_active", "")).upper() == "TRUE"),
            "upcoming_events": len(upcoming),
            "platforms_tracked": len(platforms),
            "cities_covered": len(cities),
            "added_today": added_today,
            "free_percentage": round(free_count / len(events) * 100) if events else 0,
        },
        "platform_breakdown": platform_data,
        "city_breakdown": city_data,
        "category_breakdown": category_data,
        "daily_timeline": timeline,
        "free_vs_paid": {"free": free_count, "paid": paid_count},
        "upcoming_events": upcoming,
        "recent_additions": recent,
    }
