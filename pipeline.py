"""
pipeline.py — Main Ingestion Pipeline

Orchestrates: Scrape → Deduplicate → Store in Sheets → Update Stats
"""

import asyncio
import uuid
from datetime import datetime

from scrapers import ALL_SCRAPERS
from deduplication import is_duplicate, compute_content_hash, prepare_event_row
from sheets import (
    get_spreadsheet, ensure_sheets_exist, load_existing_events,
    batch_append_events, update_stats, append_log
)
from analytics import compute_stats


async def run_scraper(scraper_class, city: str, category: str) -> list[dict]:
    """Run a single scraper for one city+category combo."""
    scraper = scraper_class()
    try:
        events = await scraper.fetch_events(city, category)
        return events
    except Exception as e:
        print(f"  ✗ {scraper.PLATFORM_NAME} failed for {city}/{category}: {e}")
        return []


async def scrape_all(cities: list[str], categories: list[str]) -> list[dict]:
    """Run all scrapers across all cities and categories concurrently."""
    print(f"\n🕷  Starting scrape: {len(cities)} cities × {len(categories)} categories × {len(ALL_SCRAPERS)} platforms")

    tasks = []
    for scraper_class in ALL_SCRAPERS:
        for city in cities:
            for category in categories:
                tasks.append(run_scraper(scraper_class, city, category))

    # Run with concurrency limit to avoid hammering servers
    semaphore = asyncio.Semaphore(5)

    async def limited_task(task):
        async with semaphore:
            return await task

    results = await asyncio.gather(*[limited_task(t) for t in tasks])

    # Flatten list of lists
    all_events = [event for result in results for event in result]
    print(f"  📥 Total raw events scraped: {len(all_events)}")
    return all_events


def deduplicate_and_store(all_events: list[dict], cities: list[str]) -> dict:
    """
    Load existing sheet data, deduplicate incoming events, store new ones.
    Returns a stats dict about the run.
    """
    print("\n🔍 Running deduplication...")

    spreadsheet = get_spreadsheet()
    ensure_sheets_exist(spreadsheet)

    # Load all existing data into memory ONCE
    existing = load_existing_events(spreadsheet)

    # Working copies of in-memory sets (we update these as we process)
    source_ids = existing["source_ids"].copy()
    content_hashes = existing["content_hashes"].copy()
    events_list = existing["events_list"].copy()

    new_rows = []
    stats = {
        "new": 0,
        "dup_exact": 0,
        "dup_hash": 0,
        "dup_fuzzy": 0,
        "errors": 0
    }

    for event in all_events:
        try:
            dup, reason = is_duplicate(event, source_ids, content_hashes, events_list)

            if dup:
                if "source_id" in reason:
                    stats["dup_exact"] += 1
                elif "hash" in reason:
                    stats["dup_hash"] += 1
                else:
                    stats["dup_fuzzy"] += 1
                continue

            # Genuine new event
            row = prepare_event_row(event)
            new_rows.append(row)

            # Update in-memory sets to catch same-batch duplicates
            content_hash = compute_content_hash(
                event.get("title", ""),
                event.get("start_date", ""),
                event.get("city", "")
            )
            source_ids.add(str(event.get("source_id", "")))
            content_hashes.add(content_hash)
            events_list.append({
                "title": event.get("title", ""),
                "start_date": event.get("start_date", ""),
                "city": event.get("city", ""),
            })

            stats["new"] += 1

        except Exception as e:
            print(f"  ⚠ Error processing event '{event.get('title', '?')}': {e}")
            stats["errors"] += 1
            continue

    # Batch append all new rows in ONE API call
    if new_rows:
        batch_append_events(spreadsheet, new_rows)

    total_stored = existing["total"] + stats["new"]
    dup_rate = round((stats["dup_exact"] + stats["dup_hash"] + stats["dup_fuzzy"]) / max(len(all_events), 1) * 100, 1)

    print(f"\n✅ Pipeline complete:")
    print(f"   New events added:     {stats['new']}")
    print(f"   Exact dups skipped:   {stats['dup_exact']}")
    print(f"   Hash dups skipped:    {stats['dup_hash']}")
    print(f"   Fuzzy dups skipped:   {stats['dup_fuzzy']}")
    print(f"   Deduplication rate:   {dup_rate}%")
    print(f"   Total in sheet:       {total_stored}")

    return {**stats, "total": total_stored, "dup_rate": dup_rate}


def refresh_stats():
    """Recompute and update the stats sheet."""
    print("\n📊 Refreshing stats sheet...")
    spreadsheet = get_spreadsheet()
    from sheets import get_all_events_for_api
    all_events = get_all_events_for_api(spreadsheet)
    stats = compute_stats(all_events)
    update_stats(spreadsheet, stats)
    print(f"  ✓ Stats updated ({len(stats)} metrics)")


async def run_full_pipeline(cities: list[str], categories: list[str]):
    """
    Full end-to-end pipeline:
    1. Scrape all platforms
    2. Deduplicate + store
    3. Refresh stats
    4. Write log entry
    """
    run_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"🚀 Pipeline Run: {run_id} | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    try:
        # Step 1: Scrape
        all_events = await scrape_all(cities, categories)

        # Step 2: Dedup + store
        result = deduplicate_and_store(all_events, cities)

        # Step 3: Refresh stats
        refresh_stats()

        # Step 4: Log the run
        spreadsheet = get_spreadsheet()
        append_log(spreadsheet, {
            "run_id": run_id,
            "timestamp": start_time.isoformat(),
            "platform": "all",
            "city": ",".join(cities),
            "scraped": len(all_events),
            "new_added": result["new"],
            "dup_exact": result["dup_exact"],
            "dup_hash": result["dup_hash"],
            "dup_fuzzy": result["dup_fuzzy"],
            "status": "success"
        })

        elapsed = (datetime.now() - start_time).seconds
        print(f"\n⏱  Total time: {elapsed}s")
        print(f"{'='*60}\n")

        return result

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")

        try:
            spreadsheet = get_spreadsheet()
            append_log(spreadsheet, {
                "run_id": run_id,
                "timestamp": start_time.isoformat(),
                "platform": "all",
                "city": ",".join(cities),
                "scraped": 0,
                "new_added": 0,
                "dup_exact": 0,
                "dup_hash": 0,
                "dup_fuzzy": 0,
                "status": f"error: {str(e)[:100]}"
            })
        except:
            pass

        raise
