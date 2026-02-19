"""
sheets.py — Google Sheets as Database
All read/write operations to Google Sheets live here.
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

EVENTS_HEADERS = [
    "content_hash", "title", "start_date", "end_date", "city",
    "country", "platform", "source_id", "url", "category",
    "price", "is_free", "organizer", "description",
    "attendee_count", "image_url", "scraped_at", "is_active"
]

STATS_HEADERS = [
    "metric", "value", "updated_at"
]

LOG_HEADERS = [
    "run_id", "timestamp", "platform", "city",
    "scraped", "new_added", "dup_exact", "dup_hash", "dup_fuzzy", "status"
]


def get_client():
    import json

    creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

    # Strip surrounding quotes if Railway added them
    creds_json_str = creds_json_str.strip()
    if creds_json_str.startswith('"') and creds_json_str.endswith('"'):
        creds_json_str = creds_json_str[1:-1]

    # Fix escaped quotes that Railway might add
    creds_json_str = creds_json_str.replace('\\"', '"')

    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)

    return gspread.authorize(creds)

def get_spreadsheet():
    client = get_client()
    sheet_id = os.getenv("SPREADSHEET_ID")
    return client.open_by_key(sheet_id)


def ensure_sheets_exist(spreadsheet):
    """Create sheets with headers if they don't exist."""
    existing = [ws.title for ws in spreadsheet.worksheets()]

    for name, headers in [
        ("events", EVENTS_HEADERS),
        ("stats", STATS_HEADERS),
        ("log", LOG_HEADERS)
    ]:
        if name not in existing:
            ws = spreadsheet.add_worksheet(title=name, rows=10000, cols=len(headers))
            ws.append_row(headers, value_input_option="USER_ENTERED")
            print(f"  ✅ Created sheet: {name}")
        else:
            ws = spreadsheet.worksheet(name)
            # Ensure headers are correct
            current_headers = ws.row_values(1)
            if current_headers != headers:
                ws.delete_rows(1)
                ws.insert_row(headers, 1)
            print(f"  ✓ Sheet exists: {name}")


def load_existing_events(spreadsheet) -> dict:
    """
    Load all events from sheet into memory.
    Returns dict with sets for fast O(1) lookup.
    """
    ws = spreadsheet.worksheet("events")
    records = ws.get_all_records()

    source_ids = set()
    content_hashes = set()
    events_list = []

    for row in records:
        if row.get("source_id"):
            source_ids.add(str(row["source_id"]))
        if row.get("content_hash"):
            content_hashes.add(str(row["content_hash"]))
        events_list.append({
            "title": row.get("title", ""),
            "start_date": str(row.get("start_date", "")),
            "city": row.get("city", ""),
        })

    print(f"  📊 Loaded {len(records)} existing events from sheet")
    return {
        "source_ids": source_ids,
        "content_hashes": content_hashes,
        "events_list": events_list,
        "total": len(records)
    }


def batch_append_events(spreadsheet, rows: list[list]):
    """Append multiple rows to events sheet in a single API call."""
    if not rows:
        return
    ws = spreadsheet.worksheet("events")
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"  ✅ Appended {len(rows)} new events to sheet")


def update_stats(spreadsheet, stats: dict):
    """Rewrite the stats sheet with latest aggregated numbers."""
    ws = spreadsheet.worksheet("stats")

    # Clear everything except header
    if ws.row_count > 1:
        ws.delete_rows(2, ws.row_count)

    now = datetime.now().isoformat()
    rows = [[metric, value, now] for metric, value in stats.items()]

    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"  📈 Updated stats sheet ({len(rows)} metrics)")


def append_log(spreadsheet, log_entry: dict):
    """Append a scrape run log entry."""
    ws = spreadsheet.worksheet("log")
    row = [log_entry.get(h, "") for h in LOG_HEADERS]
    ws.append_row(row, value_input_option="USER_ENTERED")


def get_all_events_for_api(spreadsheet) -> list[dict]:
    """Fetch all events for the dashboard API."""
    ws = spreadsheet.worksheet("events")
    return ws.get_all_records()


def get_stats_for_api(spreadsheet) -> dict:
    """Fetch stats for the dashboard API."""
    ws = spreadsheet.worksheet("stats")
    records = ws.get_all_records()
    return {r["metric"]: r["value"] for r in records}
