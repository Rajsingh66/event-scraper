# EventRadar — Complete Setup Guide

## What This System Does

- Scrapes events from **Eventbrite**, **Meetup**, and **Allevents.in**
- **Deduplicates** using 3 layers (exact ID → content hash → fuzzy title)
- Stores everything in **Google Sheets** (no database needed)
- Runs on a **schedule** every 2 hours automatically
- Shows a **live analytics dashboard** at your public URL

---

## Step 1: Install Prerequisites

```bash
# Python 3.11+
python --version

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

---

## Step 2: Google Sheets Setup (one-time)

### A) Create a Google Cloud Project
1. Go to https://console.cloud.google.com
2. Create a new project → name it "EventRadar"
3. Enable **Google Sheets API**:
   - Go to APIs & Services → Library
   - Search "Google Sheets API" → Enable

### B) Create a Service Account
1. Go to APIs & Services → Credentials
2. Click "Create Credentials" → Service Account
3. Name: "eventradar-bot" → Create
4. Click the service account → Keys tab → Add Key → JSON
5. Download the JSON file → save as `credentials.json` in this folder

### C) Create the Google Spreadsheet
1. Go to https://sheets.google.com → Create new spreadsheet
2. Name it "EventRadar Data"
3. Copy the ID from the URL:
   `https://docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit`
4. Share the spreadsheet with your service account email:
   - Click Share button
   - Paste the service account email (from credentials.json, the `client_email` field)
   - Give it **Editor** access

### D) Configure Environment
```bash
cp .env.example .env
# Edit .env and fill in:
# SPREADSHEET_ID=your_id_here
# GOOGLE_CREDENTIALS_PATH=credentials.json
```

---

## Step 3: Run Locally

```bash
python main.py
```

Visit http://localhost:8000 — your dashboard is live!

To manually trigger a scrape:
```bash
curl -X POST http://localhost:8000/api/scrape/trigger
```

Or test the pipeline directly:
```bash
python -c "
import asyncio
from pipeline import run_full_pipeline
asyncio.run(run_full_pipeline(['Mumbai', 'Bangalore'], ['technology']))
"
```

---

## Step 4: Deploy to Railway (Free Public URL)

### Option A: Railway (Recommended)
1. Push to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/eventradar.git
   git push -u origin main
   ```

2. Go to https://railway.app → New Project → Deploy from GitHub
3. Select your repo
4. Add environment variables in Railway dashboard:
   - `SPREADSHEET_ID` = your sheet ID
   - `GOOGLE_CREDENTIALS_JSON` = paste the ENTIRE contents of credentials.json
   - `SCRAPER_CITIES` = Mumbai,Delhi,Bangalore,Pune
   - `SCRAPER_CATEGORIES` = technology,music,business
   - `PORT` = 8000

5. Update `main.py` to read credentials from env var:
   ```python
   # In sheets.py, replace get_client() with:
   import json, tempfile
   def get_client():
       creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
       if creds_json:
           # Write to temp file (Railway env var)
           with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
               f.write(creds_json)
               creds_path = f.name
       else:
           creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
       creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
       return gspread.authorize(creds)
   ```

6. Railway gives you: `https://eventradar-production.railway.app` 🎉

### Option B: Render.com
Same process — connect GitHub, add env vars, deploy.
Gives you: `https://eventradar.onrender.com`

---

## Step 5: Verify Everything Works

Check these URLs:
- `GET /` — Dashboard
- `GET /api/health` — Should return `{"status": "healthy"}`
- `GET /api/config` — Shows your scraper config
- `GET /api/dashboard` — Raw analytics JSON
- `GET /api/events?city=Mumbai&limit=10` — Filtered events
- `POST /api/scrape/trigger` — Manually trigger a scrape

---

## Understanding Deduplication

### Layer 1 — Exact Source ID
Each platform assigns its own unique ID to every event.
If we've seen `eventbrite:event_123456` before → skip.

### Layer 2 — Content Hash
SHA-256 of: `normalized_title | YYYY-MM-DD | normalized_city`
Catches the same real-world event listed on multiple platforms.

### Layer 3 — Fuzzy Title Match
`fuzz.token_sort_ratio("React Conf Mumbai", "React Conference Mumbai") = 91%`
If ≥ 85% similar AND same date AND same city → duplicate.

---

## Google Sheets Structure

| Sheet | Contents |
|-------|----------|
| `events` | All scraped events (master data) |
| `stats`  | Aggregated metrics, updated every scrape |
| `log`    | Every scrape run with counts |

---

## Customizing

**Add more cities** — edit `SCRAPER_CITIES` in `.env`

**Add more categories** — edit `SCRAPER_CATEGORIES` in `.env`

**Change scrape frequency** — edit `SCRAPE_INTERVAL_HOURS` in `.env`

**Add a new platform scraper:**
1. Create `scrapers/yourplatform.py` extending `BaseScraper`
2. Implement `async def fetch_events(self, city, category) -> list[dict]`
3. Add it to `scrapers/__init__.py`'s `ALL_SCRAPERS` list

---

## Project Structure

```
event-scraper/
├── main.py              ← FastAPI app + scheduler
├── pipeline.py          ← Orchestrates scrape → dedup → store
├── deduplication.py     ← 3-layer dedup engine
├── sheets.py            ← Google Sheets read/write
├── analytics.py         ← Compute stats from events
├── scrapers/
│   ├── base.py          ← Base scraper class
│   ├── eventbrite.py    ← Eventbrite scraper
│   ├── meetup.py        ← Meetup GraphQL scraper
│   └── allevents.py     ← Allevents.in scraper
├── static/
│   └── index.html       ← Dashboard UI
├── credentials.json     ← Google service account (DON'T commit this!)
├── .env                 ← Your config (DON'T commit this!)
├── .env.example         ← Template
├── requirements.txt     ← Python deps
└── Dockerfile           ← For deployment
```

---

## ⚠️ Important Notes

1. **Never commit `credentials.json` or `.env` to git** — add both to `.gitignore`
2. The scrapers include fallback demo data when sites block scraping — this lets you test the full pipeline even locally
3. Google Sheets API has a limit of 300 writes/minute — the batch write approach keeps us well under this
4. Always respect `robots.txt` and add delays between requests (already built in)
