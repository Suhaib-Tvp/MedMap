#!/usr/bin/env python3
"""
MedMap — Streamlit App
Interactive web interface for retrieving place data from Google Maps Places API.
"""

import csv
import io
import json
import logging
import time
import datetime
import os
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st
import pandas as pd
from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Logging & Constants
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
MAX_PAGES = 3
PAGE_TOKEN_DELAY_SECONDS = 1.0
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
# Database Setup & Helpers (Supabase)
# ============================================================================
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
    key = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))
    return create_client(url, key)

supabase: Client = init_supabase()

def log_api_usage(count=1):
    try:
        now = datetime.datetime.utcnow().isoformat()
        data = [{"timestamp": now} for _ in range(count)]
        supabase.table("api_usage").insert(data).execute()
    except Exception as e:
        logger.error(f"Failed to log API usage: {e}")

def get_monthly_api_usage() -> int:
    try:
        now = datetime.datetime.now()
        start_of_month = datetime.datetime(now.year, now.month, 1).isoformat()
        response = supabase.table("api_usage").select("*", count="exact").gte("timestamp", start_of_month).execute()
        return response.count if response.count is not None else 0
    except Exception as e:
        logger.error(f"Failed to fetch API usage count: {e}")
        return 0

def log_search(city: str, keyword: str):
    try:
        supabase.table("search_history").insert({"city": city, "keyword": keyword}).execute()
    except Exception as e:
        logger.error(f"Failed to log search: {e}")

def get_recent_searches(limit=10) -> List[Tuple[str, str, str]]:
    try:
        response = supabase.table("search_history").select("city, keyword, timestamp").order("timestamp", desc=True).limit(limit).execute()
        return [(r['city'], r['keyword'], r['timestamp']) for r in response.data]
    except Exception as e:
        logger.error(f"Failed to fetch recent searches: {e}")
        return []

def log_download(city: str, keyword: str):
    try:
        supabase.table("downloads").insert({"city": city, "keyword": keyword}).execute()
    except Exception as e:
        logger.error(f"Failed to log download: {e}")

def get_recent_downloads(limit=5) -> List[Tuple[str, str, str]]:
    try:
        response = supabase.table("downloads").select("city, keyword, timestamp").order("timestamp", desc=True).limit(limit).execute()
        return [(r['city'], r['keyword'], r['timestamp']) for r in response.data]
    except Exception as e:
        logger.error(f"Failed to fetch recent downloads: {e}")
        return []



# ============================================================================
# API Search & Processing Functions
# ============================================================================
def _fetch_one_page(
    api_key: str, query: str, page_token: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch a single page of Places results. Returns (places, next_page_token)."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.rating,places.userRatingCount,places.websiteUri,"
            "places.nationalPhoneNumber,places.internationalPhoneNumber,"
            "nextPageToken"
        ),
    }
    payload: Dict[str, Any] = {"textQuery": query}
    if page_token:
        payload["pageToken"] = page_token

    resp = requests.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=payload, timeout=30)
    log_api_usage(1)

    if resp.status_code == 200:
        data = resp.json()
        places = data.get("places", [])
        next_token = data.get("nextPageToken")
        return places, next_token
    else:
        logger.error(f"Places API error {resp.status_code}: {resp.text}")
        return [], None


def fetch_places_batch(
    api_key: str, category: str, city: str,
    page_token: Optional[str] = None, max_pages: int = MAX_PAGES
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch up to max_pages of results. Returns (all_places, last_next_page_token)."""
    all_raw: List[Dict[str, Any]] = []
    query = f"{category} in {city}"
    token = page_token

    for _ in range(max_pages):
        places, token = _fetch_one_page(api_key, query, token)
        all_raw.extend(places)
        if not token:
            break
        time.sleep(PAGE_TOKEN_DELAY_SECONDS)

    return all_raw, token

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

    st.markdown('<h1 class="hero-title">📍 MedMap</h1>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Discover places in any city — powered by Google Maps</p>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("## ⚙️ Search Settings")
        
        google_key = st.text_input("🔑 Google Maps API Key", type="password", help="Paste your active Google Cloud API key here")
        
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
                st.caption(f"{s_cat} in {s_city} ({s_time[:16].replace('T', ' ')})")
        else:
            st.caption("No recent searches.")
            
        st.markdown("---")
        
        # 8. Downloaded Datasets
        st.markdown("## 📥 Downloaded Datasets")
        recent_dl = get_recent_downloads()
        if recent_dl:
            for d_city, d_cat, d_time in recent_dl:
                st.caption(f"{d_city}_{d_cat} ({d_time[:16].replace('T', ' ')})")
        else:
            st.caption("No recent downloads.")
            
        st.markdown("<div style='color:#55556e;font-size:0.75rem;text-align:center;margin-top:20px'>Data via Google Maps Places API</div>", unsafe_allow_html=True)

    if search_clicked:
        if usage_error:
            st.error("Cannot perform search: API limit reached. Please check back next month.")
            return
        if not google_key:
            st.error("🔑 **Google Maps API Key** is missing. Paste your key in the sidebar.")
            return

        log_search(city, category)

        with st.spinner(f"Searching for {category} in {city}..."):
            raw_results, next_token = fetch_places_batch(google_key, category, city)

        # Deduplication
        seen = set()
        unique_places = []
        for r in raw_results:
            pid = r.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                unique_places.append(r)

        if not unique_places:
            st.warning("😕 No results found. Try a different keyword or city.")
            return

        # Extract details
        target_city_lower = city.split(",")[0].strip().lower()
        batch = []
        for place in unique_places:
            details = extract_place_details(place, default_city=target_city_lower)
            batch.append(details)

        if not batch:
            st.warning("😕 No results found.")
            return

        st.session_state["results"] = batch
        st.session_state["all_results"] = list(batch)  # cumulative across rounds
        st.session_state["current_batch"] = list(batch)
        st.session_state["seen_ids"] = seen
        st.session_state["next_page_token"] = next_token
        st.session_state["search_round"] = 1
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
        
        search_round = st.session_state.get("search_round", 1)
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
                <div class="metric-card">
                    <div class="value">{search_round}</div>
                    <div class="label">Search Round</div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )

        df = pd.DataFrame(results)
        display_cols = ["Name", "City", "Address", "Phone", "Website URL", "Rating", "Reviews"]
        df_display = df[[c for c in display_cols if c in df.columns]]
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=min(len(df_display)*38+50, 600))

        # ---------- Load More Button ----------
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        if google_key:
            next_token = st.session_state.get("next_page_token")
            if next_token:
                if st.button("➕ Load More Results", use_container_width=True, key="load_more"):
                    with st.spinner("Fetching more results..."):
                        more_raw, new_token = fetch_places_batch(
                            google_key,
                            st.session_state["category"],
                            st.session_state["city"],
                            page_token=next_token,
                            max_pages=MAX_PAGES,
                        )

                    seen_ids = st.session_state.get("seen_ids", set())
                    target_city_lower = st.session_state["city"].split(",")[0].strip().lower()
                    new_batch = []
                    for r in more_raw:
                        pid = r.get("id")
                        if pid and pid not in seen_ids:
                            seen_ids.add(pid)
                            details = extract_place_details(r, default_city=target_city_lower)
                            new_batch.append(details)

                    if new_batch:
                        st.session_state["results"].extend(new_batch)
                        st.session_state["all_results"].extend(new_batch)
                        st.session_state["current_batch"] = new_batch
                        st.session_state["seen_ids"] = seen_ids
                        st.session_state["search_round"] = st.session_state.get("search_round", 1) + 1

                    st.session_state["next_page_token"] = new_token
                    st.rerun()
            else:
                st.info("✅ All available results have been loaded. No more pages from Google.")
        
        # ---------- Downloads Section ----------
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("##### 📥 Download Results")
        
        s_city = st.session_state["city"]
        s_cat = st.session_state["category"]
        safe_city = s_city.split(",")[0].strip().replace(" ", "_").lower()
        safe_cat = s_cat.strip().replace(" ", "_").lower()
        base_filename = f"{safe_city}_{safe_cat}"

        current_batch = st.session_state.get("current_batch", results)
        all_results = st.session_state.get("all_results", results)
        
        strip_current = [{k:v for k,v in h.items() if k != "place_id"} for h in current_batch]
        strip_all = [{k:v for k,v in h.items() if k != "place_id"} for h in all_results]

        st.markdown(f"**Current Batch:** {len(strip_current)} records &nbsp;|&nbsp; **All Batches:** {len(strip_all)} records")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.download_button(
                "📄 Current Batch CSV",
                data=to_csv_bytes(strip_current),
                file_name=f"{base_filename}_batch.csv",
                mime="text/csv",
                use_container_width=True,
                on_click=log_download_callback,
                args=(s_city, s_cat)
            )
        with c2:
            st.download_button(
                "📄 Current Batch JSON",
                data=to_json_bytes(strip_current),
                file_name=f"{base_filename}_batch.json",
                mime="application/json",
                use_container_width=True,
                on_click=log_download_callback,
                args=(s_city, s_cat)
            )
        with c3:
            st.download_button(
                "📦 All Batches CSV",
                data=to_csv_bytes(strip_all),
                file_name=f"{base_filename}_all.csv",
                mime="text/csv",
                use_container_width=True,
                on_click=log_download_callback,
                args=(s_city, s_cat)
            )
        with c4:
            st.download_button(
                "📦 All Batches JSON",
                data=to_json_bytes(strip_all),
                file_name=f"{base_filename}_all.json",
                mime="application/json",
                use_container_width=True,
                on_click=log_download_callback,
                args=(s_city, s_cat)
            )

    st.markdown('<div class="footer">MedMap · Built with Streamlit & Google Maps Places API</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
