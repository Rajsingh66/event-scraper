"""
main.py — FastAPI Application + APScheduler

Serves:
  - REST API for dashboard (/api/*)
  - Static dashboard HTML (/)
  - Triggers scrape runs on schedule
"""

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

from pipeline import run_full_pipeline
from sheets import get_spreadsheet, ensure_sheets_exist, get_all_events_for_api, get_stats_for_api
from analytics import compute_dashboard_data

# ── Config ──────────────────────────────────────────────────────
CITIES = [c.strip() for c in os.getenv("SCRAPER_CITIES", "Mumbai,Delhi,Bangalore,Pune").split(",")]
CATEGORIES = [c.strip() for c in os.getenv("SCRAPER_CATEGORIES", "technology,music,business").split(",")]
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL_HOURS", "2"))

# ── Scheduler ───────────────────────────────────────────────────
scheduler = AsyncIOScheduler()

async def scheduled_scrape():
    print(f"\n⏰ Scheduled scrape triggered at {datetime.now()}")
    await run_full_pipeline(CITIES, CATEGORIES)

# ── App Lifecycle ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Event Scraper API...")
    print(f"   Cities: {CITIES}")
    print(f"   Categories: {CATEGORIES}")
    print(f"   Scrape interval: every {SCRAPE_INTERVAL}h")

    # Ensure Google Sheets structure exists
    try:
        spreadsheet = get_spreadsheet()
        ensure_sheets_exist(spreadsheet)
        print("   ✅ Google Sheets connected")
    except Exception as e:
        print(f"   ⚠ Google Sheets connection failed: {e}")

    # Schedule scraping
    scheduler.add_job(
        scheduled_scrape,
        "interval",
        hours=SCRAPE_INTERVAL,
        id="scrape_job",
        replace_existing=True
    )
    scheduler.start()
    print(f"   ✅ Scheduler started (every {SCRAPE_INTERVAL}h)")

    yield  # App runs here

    # Shutdown
    scheduler.shutdown()
    print("👋 Scheduler stopped")


# ── FastAPI App ──────────────────────────────────────────────────
app = FastAPI(
    title="Event Scraper API",
    description="Scrapes events from multiple platforms, deduplicates, and stores in Google Sheets",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Routes ───────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.post("/api/scrape/trigger")
async def trigger_scrape(background_tasks: BackgroundTasks):
    """Manually trigger a scrape run."""
    background_tasks.add_task(run_full_pipeline, CITIES, CATEGORIES)
    return {
        "message": "Scrape triggered in background",
        "cities": CITIES,
        "categories": CATEGORIES,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/dashboard")
async def get_dashboard_data():
    """
    Main endpoint for the dashboard.
    Returns all analytics data in one call.
    """
    try:
        spreadsheet = get_spreadsheet()
        events = get_all_events_for_api(spreadsheet)
        data = compute_dashboard_data(events)
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events")
async def get_events(
    city: str = "",
    platform: str = "",
    category: str = "",
    is_free: str = "",
    limit: int = 50,
    offset: int = 0
):
    """Get events with optional filtering."""
    try:
        spreadsheet = get_spreadsheet()
        all_events = get_all_events_for_api(spreadsheet)

        # Apply filters
        filtered = all_events
        if city:
            filtered = [e for e in filtered if city.lower() in e.get("city", "").lower()]
        if platform:
            filtered = [e for e in filtered if e.get("platform", "").lower() == platform.lower()]
        if category:
            filtered = [e for e in filtered if category.lower() in e.get("category", "").lower()]
        if is_free:
            want_free = is_free.lower() == "true"
            filtered = [e for e in filtered if str(e.get("is_free", "")).upper() == ("TRUE" if want_free else "FALSE")]

        total = len(filtered)
        paginated = filtered[offset:offset + limit]

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "events": paginated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Get latest stats from the stats sheet."""
    try:
        spreadsheet = get_spreadsheet()
        stats = get_stats_for_api(spreadsheet)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
async def get_config():
    """Return current scraper configuration."""
    return {
        "cities": CITIES,
        "categories": CATEGORIES,
        "scrape_interval_hours": SCRAPE_INTERVAL,
        "platforms": ["eventbrite", "meetup", "allevents"],
    }


# ── Serve Dashboard HTML ─────────────────────────────────────────
# Dashboard is served from static/index.html
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    dashboard_path = "static/index.html"
    if os.path.exists(dashboard_path):
        # Add encoding="utf-8" to handle special characters correctly
        with open(dashboard_path, mode="r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>Dashboard not found.</h1>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
