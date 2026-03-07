#!/usr/bin/env python3
"""
MedMap — Streamlit App
Interactive web interface for retrieving place data from Google Maps Places API.
"""

import csv
import io
import json
import logging
import sqlite3
import time
import uuid
import datetime
import os
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# Logging & Constants
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
MAX_PAGES = 3
PAGE_TOKEN_DELAY_SECONDS = 1.0
DB_NAME = "medmap_history.db"
API_LIMIT_MONTHLY = 1000

# ============================================================================
# Page config & CSS
# ============================================================================
st.set_page_config(page_title="MedMap Place Finder", page_icon="📍", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    /* ---------- Google Font ---------- */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="st-"] {
        font-family: 'Inter', sans-serif;
    }

    /* ---------- Main background ---------- */
    .stApp {
        background: linear-gradient(135deg, #0f0c29 0%, #1a1a2e 40%, #16213e 100%);
    }

    /* ---------- Sidebar ---------- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #0f0c29 100%);
        border-right: 1px solid rgba(255,255,255,0.06);
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown label,
    section[data-testid="stSidebar"] .stMarkdown span {
        color: #c4c4d8 !important;
    }

    /* ---------- Hero header ---------- */
    .hero-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(90deg, #00d2ff 0%, #7b68ee 50%, #ff6ec7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0;
        letter-spacing: -0.5px;
    }
    .hero-sub {
        text-align: center;
        color: #8888a8;
        font-size: 1.05rem;
        margin-top: 0;
        margin-bottom: 2rem;
    }

    /* ---------- Metric cards ---------- */
    .metric-row {
        display: flex;
        gap: 1rem;
        justify-content: center;
        margin-bottom: 1.5rem;
        flex-wrap: wrap;
    }
    .metric-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 1.2rem 2rem;
        text-align: center;
        min-width: 160px;
        backdrop-filter: blur(12px);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.35);
    }
    .metric-card .value {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #00d2ff, #7b68ee);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .metric-card .label {
        font-size: 0.8rem;
        color: #8888a8;
        margin-top: 4px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    /* ---------- Dataframe ---------- */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }

    /* ---------- Buttons ---------- */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #7b68ee 0%, #00d2ff 100%) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.55rem 1.8rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.3px;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .stDownloadButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(123,104,238,0.45) !important;
    }

    div.stButton > button {
        background: linear-gradient(135deg, #ff6ec7 0%, #7b68ee 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.6rem 2.2rem !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        width: 100% !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(255,110,199,0.45) !important;
    }

    /* ---------- Section divider ---------- */
    .section-divider {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(123,104,238,0.3), transparent);
        margin: 2rem 0;
    }

    /* ---------- Footer ---------- */
    .footer {
        text-align: center;
        color: #55556e;
        font-size: 0.78rem;
        margin-top: 3rem;
        padding: 1rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# Database Setup & Helpers
# ============================================================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city TEXT,
                    keyword TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city TEXT,
                    keyword TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE,
                    city TEXT,
                    keyword TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def log_api_usage(count=1):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for _ in range(count):
        c.execute("INSERT INTO api_usage DEFAULT VALUES")
    conn.commit()
    conn.close()

def get_monthly_api_usage():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM api_usage WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')")
    count = c.fetchone()[0]
    conn.close()
    return count

def log_search(city, keyword):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO search_history (city, keyword) VALUES (?, ?)", (city, keyword))
    conn.commit()
    conn.close()

def get_recent_searches(limit=10):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT city, keyword, timestamp FROM search_history ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def log_download(city, keyword):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO downloads (city, keyword) VALUES (?, ?)", (city, keyword))
    conn.commit()
    conn.close()

def get_recent_downloads(limit=5):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT city, keyword, timestamp FROM downloads ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def update_user_session(session_id, city="", keyword=""):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''INSERT INTO user_sessions (session_id, city, keyword, timestamp) 
                 VALUES (?, ?, ?, CURRENT_TIMESTAMP) 
                 ON CONFLICT(session_id) 
                 DO UPDATE SET city=excluded.city, keyword=excluded.keyword, timestamp=CURRENT_TIMESTAMP''', 
              (session_id, city, keyword))
    conn.commit()
    conn.close()

def get_active_users_count():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT session_id) FROM user_sessions WHERE timestamp >= datetime('now', '-1 day')")
    count = c.fetchone()[0]
    conn.close()
    return count

# ============================================================================
# API Search & Processing Functions
# ============================================================================
@st.cache_data(show_spinner=False, ttl=86400)
def geocode_city(_api_key: str, city: str) -> Tuple[Optional[float], Optional[float]]:
    params = {"address": city, "key": _api_key}
    resp = requests.get(GEOCODING_URL, params=params, timeout=10)
    log_api_usage(1)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    return None, None

def generate_grid(center_lat: float, center_lng: float) -> List[Tuple[float, float]]:
    # 3x3 grid around city. Spacing ~0.025 deg (approx 2.5km apart)
    offset = 0.025
    grid = []
    for dlat in [-offset, 0, offset]:
        for dlng in [-offset, 0, offset]:
            grid.append((center_lat + dlat, center_lng + dlng))
    return grid

@st.cache_data(show_spinner=False, ttl=86400)
def perform_grid_search(_api_key: str, category: str, grid: List[Tuple[float, float]], radius: float = 2500.0) -> List[Dict[str, Any]]:
    all_raw = []
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.rating,places.userRatingCount,places.websiteUri,"
            "places.nationalPhoneNumber,places.internationalPhoneNumber,"
            "nextPageToken"
        ),
    }

    for lat, lng in grid:
        page_token = None
        for _ in range(MAX_PAGES):
            payload = {"textQuery": category}
            if page_token:
                payload["pageToken"] = page_token
            payload["locationBias"] = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": radius
                }
            }
            resp = requests.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=payload, timeout=30)
            log_api_usage(1)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("places", [])
                all_raw.extend(results)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
                time.sleep(PAGE_TOKEN_DELAY_SECONDS)
            else:
                break
    return all_raw

def extract_place_details(place: Dict[str, Any], default_city: str = "") -> Dict[str, str]:
    name_dict = place.get("displayName", {})
    name = name_dict.get("text", "N/A") if isinstance(name_dict, dict) else "N/A"
    address = place.get("formattedAddress", "N/A")
    
    city = default_city
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        city = parts[-3].strip()

    return {
        "Name": name,
        "City": city,
        "Address": address,
        "Phone": place.get("nationalPhoneNumber", place.get("internationalPhoneNumber", "")),
        "Website URL": place.get("websiteUri", ""),
        "Rating": str(place.get("rating", "")),
        "Reviews": str(place.get("userRatingCount", "")),
        "place_id": place.get("id", ""),
    }

def to_csv_bytes(records: List[Dict[str, str]]) -> bytes:
    if not records:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue().encode("utf-8")

def to_json_bytes(records: List[Dict[str, str]]) -> bytes:
    return json.dumps(records, indent=2, ensure_ascii=False).encode("utf-8")

def log_download_callback(city, keyword):
    log_download(city, keyword)

# ============================================================================
# Main UI
# ============================================================================
def main() -> None:
    init_db()

    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
        update_user_session(st.session_state["session_id"])

    st.markdown('<h1 class="hero-title">📍 MedMap</h1>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Discover places in any city — powered by Google Maps</p>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("## ⚙️ Search Settings")
        
        # Check Streamlit secrets or OS environment for the key first
        secure_key = ""
        try:
            secure_key = st.secrets.get("GOOGLE_MAPS_API_KEY", "")
        except Exception:
            pass
            
        if not secure_key:
            secure_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
            
        if secure_key:
            google_key = secure_key
            st.success("✅ Secure API Key Loaded")
        else:
            google_key = st.text_input("🔑 API Key", type="password", help="Get yours at Google Cloud Console")
        
        category = st.text_input("🏷️ Search keyword", value="hospital", placeholder="hospital")
        city = st.text_input("🌍 City Name", value="Hyderabad, India", placeholder="e.g. New Delhi, India")
        search_clicked = st.button("🔍  Search", use_container_width=True)

        st.markdown("---")
        
        # 11, 12. API Usage Dashboard & Alerts
        st.markdown("## 📊 Google API Usage")
        monthly_usage = get_monthly_api_usage()
        remaining = max(0, API_LIMIT_MONTHLY - monthly_usage)
        usage_pct = (monthly_usage / API_LIMIT_MONTHLY) * 100

        st.metric("Monthly Requests", f"{monthly_usage} / {API_LIMIT_MONTHLY}")
        st.metric("Remaining Requests", remaining)
        st.progress(min(usage_pct / 100, 1.0))

        usage_error = False
        if usage_pct >= 100:
            st.error("🚨 Monthly API limit reached. Stop API calls.")
            usage_error = True
        elif usage_pct >= 90:
            st.error("🚨 Danger: API usage > 90%!")
        elif usage_pct >= 70:
            st.warning("⚠ API usage getting high this month.")
            
        st.markdown("---")
        
        # 7. Search History
        st.markdown("## 🕒 Search History")
        recent_searches = get_recent_searches()
        if recent_searches:
            for s_city, s_cat, s_time in recent_searches:
                st.caption(f"{s_cat} in {s_city} ({s_time[:16]})")
        else:
            st.caption("No recent searches.")
            
        st.markdown("---")
        
        # 8. Downloaded Datasets
        st.markdown("## 📥 Downloaded Datasets")
        recent_dl = get_recent_downloads()
        if recent_dl:
            for d_city, d_cat, d_time in recent_dl:
                st.caption(f"{d_city}_{d_cat} ({d_time[:16]})")
        else:
            st.caption("No recent downloads.")
            
        st.markdown("---")

        # 13. Session Activity
        st.markdown("## 👥 Session Activity")
        active_users = get_active_users_count()
        st.metric("Active Users (Last 24h)", active_users)

        st.markdown("<div style='color:#55556e;font-size:0.75rem;text-align:center;margin-top:20px'>Data via Google Maps Places API</div>", unsafe_allow_html=True)

    if search_clicked:
        if usage_error:
            st.error("Cannot perform search: API limit reached. Please check back next month.")
            return
        if not google_key:
            st.error("🔑 **Google Maps API Key** is missing. Paste your key in the sidebar.")
            return

        update_user_session(st.session_state["session_id"], city, category)
        log_search(city, category)

        with st.spinner("Finding city coordinates..."):
            lat, lng = geocode_city(google_key, city)
            
        if lat is None:
            st.error(f"Could not find coordinates for city: {city}. Check spelling or API Key permissions.")
            return

        grid = generate_grid(lat, lng)

        with st.spinner("Executing 3x3 Grid Search (fetching 9 regions)..."):
            raw_results = perform_grid_search(google_key, category, grid)

        # Deduplication
        seen = set()
        unique_places = []
        for r in raw_results:
            pid = r.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                unique_places.append(r)

        if not unique_places:
            st.warning("😕 No results found. You may have exhausted the area.")
            return

        # Filtering strictly to searched city
        target_city_lower = city.split(",")[0].strip().lower()
        batch = []
        for place in unique_places:
            details = extract_place_details(place, default_city=target_city_lower)
            addr_lower = details["Address"].lower()
            city_lower = details["City"].lower()
            
            if target_city_lower in addr_lower or target_city_lower == city_lower:
                batch.append(details)
                
        if not batch:
            st.warning("😕 No results strictly matched the searched city.")
            return
            
        st.session_state["results"] = batch
        st.session_state["city"] = city
        st.session_state["category"] = category

    results = st.session_state.get("results", [])
    if results:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        
        # Calculate stats
        avg_rating = 0
        rated_count = 0
        total_reviews = 0
        for h in results:
            try:
                avg_rating += float(h["Rating"])
                rated_count += 1
            except ValueError:
                pass
            try:
                total_reviews += int(h["Reviews"])
            except ValueError:
                pass
        avg_rating = round(avg_rating / rated_count, 1) if rated_count else 0
        
        st.markdown(
            f"""
            <div class="metric-row">
                <div class="metric-card">
                    <div class="value">{len(results)}</div>
                    <div class="label">Total Unique Results</div>
                </div>
                <div class="metric-card">
                    <div class="value">⭐ {avg_rating}</div>
                    <div class="label">Avg Rating</div>
                </div>
                <div class="metric-card">
                    <div class="value">{total_reviews:,}</div>
                    <div class="label">Total Reviews</div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )

        df = pd.DataFrame(results)
        display_cols = ["Name", "City", "Address", "Phone", "Website URL", "Rating", "Reviews"]
        df_display = df[[c for c in display_cols if c in df.columns]]
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=min(len(df_display)*38+50, 600))
        
        # Downloads
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("##### 📥 Download Results")
        
        s_city = st.session_state["city"]
        s_cat = st.session_state["category"]
        safe_city = s_city.split(",")[0].strip().replace(" ", "_").lower()
        safe_cat = s_cat.strip().replace(" ", "_").lower()
        base_filename = f"{safe_city}_{safe_cat}"
        
        strip_pid = [{k:v for k,v in h.items() if k != "place_id"} for h in results]

        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            st.download_button(
                "CSV Dataset",
                data=to_csv_bytes(strip_pid),
                file_name=f"{base_filename}.csv",
                mime="text/csv",
                use_container_width=True,
                on_click=log_download_callback,
                args=(s_city, s_cat)
            )
        with c2:
            st.download_button(
                "JSON Dataset",
                data=to_json_bytes(strip_pid),
                file_name=f"{base_filename}.json",
                mime="application/json",
                use_container_width=True,
                on_click=log_download_callback,
                args=(s_city, s_cat)
            )

    st.markdown('<div class="footer">MedMap · Built with Streamlit & Google Maps Places API</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
