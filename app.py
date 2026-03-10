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
import urllib3
import streamlit as st
import pandas as pd
from supabase import create_client, Client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Logging & Constants
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
MAX_PAGES = 3
PAGE_TOKEN_DELAY_SECONDS = 2
API_LIMIT_MONTHLY = 1000

# Compass offsets (lat_delta, lng_delta) used by "Load More" to bias
# the search toward different parts of the city.  ~0.045° ≈ 5 km.
SEARCH_OFFSETS = [
    ( 0.045,  0.000),   # N
    ( 0.045,  0.045),   # NE
    ( 0.000,  0.045),   # E
    (-0.045,  0.045),   # SE
    (-0.045,  0.000),   # S
    (-0.045, -0.045),   # SW
    ( 0.000, -0.045),   # W
    ( 0.045, -0.045),   # NW
    ( 0.090,  0.000),   # far N
    ( 0.000,  0.090),   # far E
    (-0.090,  0.000),   # far S
    ( 0.000, -0.090),   # far W
    ( 0.090,  0.090),   # far NE
    (-0.090, -0.090),   # far SW
    ( 0.090, -0.090),   # far NW
    (-0.090,  0.090),   # far SE
]

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

    /* Fix Material Icons displaying as text (e.g. keyboard_double_arrow_right) */
    .material-symbols-rounded, .stIcon {
        font-family: 'Material Symbols Rounded' !important;
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
# Google Maps Places API — Text Search
# ============================================================================
KEYWORDS = [
    'pmr', 'physical medical', 'physical medicine', 'physiotherapy', 
    'rehabilitation', 'rehab', 'neuro', 'neuro science', 
    'neuro surgery', 'neurology', 'orthopaedic', 'orthopedic', 'orthopaedics'
]

def check_departments(url: Any) -> str:
    if pd.isna(url) or not isinstance(url, str) or not url.strip():
        return "No Website"
    
    if not url.startswith('http'):
        url = 'http://' + url
        
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        
        if res.status_code == 200:
            text = res.text.lower()
            found_terms = [word for word in KEYWORDS if word in text]
            if found_terms:
                return ", ".join(list(dict.fromkeys(found_terms)))
            else:
                return "Not found on homepage"
        else:
            return f"Error ({res.status_code})"
    except Exception:
        return "Failed to access"

def _search_places_page(
    api_key: str,
    query: str,
    page_token: Optional[str] = None,
    location: Optional[str] = None,
    radius: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Execute a single Places Text Search request."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.rating,places.userRatingCount,"
            "places.websiteUri,places.nationalPhoneNumber,"
            "places.internationalPhoneNumber,"
            "nextPageToken"
        ),
    }
    payload: Dict[str, Any] = {"textQuery": query}
    if page_token:
        payload["pageToken"] = page_token
    if location and radius:
        lat_str, lng_str = location.split(",")
        payload["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": float(lat_str),
                    "longitude": float(lng_str),
                },
                "radius": float(radius),
            }
        }

    resp = requests.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=payload, timeout=30)
    log_api_usage(1)

    if resp.status_code == 200:
        data = resp.json()
        return data.get("places", []), data.get("nextPageToken")
    else:
        logger.error(f"Places API error {resp.status_code}: {resp.text}")
        return [], None


def fetch_all_places(
    api_key: str,
    search_category: str,
    city: str,
    location: Optional[str] = None,
    radius: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch all results with automatic pagination (up to MAX_PAGES)."""
    query = search_category if location else f"{search_category} in {city}"
    all_results: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    for page_num in range(1, MAX_PAGES + 1):
        results, page_token = _search_places_page(
            api_key, query, page_token, location, radius
        )
        all_results.extend(results)
        if not page_token:
            break
        time.sleep(PAGE_TOKEN_DELAY_SECONDS)

    return all_results


def compute_centroid(places: List[Dict[str, Any]]) -> Tuple[float, float]:
    """Return the average (lat, lng) from a list of raw place results."""
    lats, lngs = [], []
    for p in places:
        loc = p.get("location", {})
        if "latitude" in loc and "longitude" in loc:
            lats.append(loc["latitude"])
            lngs.append(loc["longitude"])
    if not lats:
        return 0.0, 0.0
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


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
    # ---- Initialise session state ----
    if "all_results" not in st.session_state:
        st.session_state["all_results"] = []
    if "current_batch" not in st.session_state:
        st.session_state["current_batch"] = []
    if "seen_ids" not in st.session_state:
        st.session_state["seen_ids"] = set()
    if "search_round" not in st.session_state:
        st.session_state["search_round"] = 0
    if "city_center" not in st.session_state:
        st.session_state["city_center"] = (0.0, 0.0)
    if "raw_cache" not in st.session_state:
        st.session_state["raw_cache"] = []

    st.markdown('<h1 class="hero-title">📍 MedMap</h1>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Discover places in any city — powered by Google Maps</p>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("## ⚙️ Search Settings")
        google_key = st.text_input("🔑 Google Maps API Key", type="password", help="Paste your active Google Cloud API key here")
        category = st.text_input("🏷️ Search keyword", value="hospital", placeholder="hospital")
        city = st.text_input("🌍 City Name", value="Hyderabad, India", placeholder="e.g. New Delhi, India")
        search_clicked = st.button("🔍  Search", use_container_width=True)

        st.markdown("---")
        
        # Filter Section
        st.markdown("## 🏥 Filter Departments")
        filter_source = st.selectbox(
            "Select data to filter:",
            ["Current Batch", "All Searches", "Upload CSV"]
        )
        
        uploaded_csv = None
        if filter_source == "Upload CSV":
            uploaded_csv = st.file_uploader("Upload CSV file", type=["csv"])
            
        filter_clicked = st.button("⚙️ Apply Department Filter", use_container_width=True)

        st.markdown("---")

        # API Usage Dashboard
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

        # Search History
        st.markdown("## 🕒 Search History")
        recent_searches = get_recent_searches()
        if recent_searches:
            for s_city, s_cat, s_time in recent_searches:
                st.caption(f"{s_cat} in {s_city} ({s_time[:16].replace('T', ' ')})")
        else:
            st.caption("No recent searches.")

        st.markdown("---")

        # Downloaded Datasets
        st.markdown("## 📥 Downloaded Datasets")
        recent_dl = get_recent_downloads()
        if recent_dl:
            for d_city, d_cat, d_time in recent_dl:
                st.caption(f"{d_city}_{d_cat} ({d_time[:16].replace('T', ' ')})")
        else:
            st.caption("No recent downloads.")

        st.markdown("<div style='color:#55556e;font-size:0.75rem;text-align:center;margin-top:20px'>Data via Google Maps Places API</div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Helper: run one search round, deduplicate, and append to state
    # ------------------------------------------------------------------
    def _run_search_round(
        google_key: str,
        search_category: str,
        city: str,
        location: Optional[str] = None,
        radius: Optional[int] = None,
    ) -> None:
        with st.spinner("Searching Google Maps …"):
            raw_results = fetch_all_places(google_key, search_category, city, location, radius)

        # Filter out duplicates
        new_results = [
            r for r in raw_results
            if r.get("id") and r["id"] not in st.session_state["seen_ids"]
        ]

        if not new_results:
            st.warning("😕 No new results found. You may have exhausted the area.")
            return

        # Extract details and filter by city
        target_city_lower = city.split(",")[0].strip().lower()
        batch: List[Dict[str, str]] = []
        for place in new_results:
            details = extract_place_details(place, default_city=target_city_lower)
            addr_lower = details["Address"].lower()
            city_lower = details["City"].lower()
            if target_city_lower in addr_lower or target_city_lower == city_lower:
                batch.append(details)

        if not batch:
            st.warning("😕 No results strictly matched the searched city.")
            return

        # Update session state
        for h in batch:
            st.session_state["seen_ids"].add(h["place_id"])
        st.session_state["current_batch"] = batch
        st.session_state["all_results"].extend(batch)

        # Store raw results for centroid
        st.session_state["raw_cache"].extend(new_results)
        st.session_state["city_center"] = compute_centroid(st.session_state["raw_cache"])

    # ------------------------------------------------------------------
    # "Search" button — fresh search, resets state
    # ------------------------------------------------------------------
    if search_clicked:
        if usage_error:
            st.error("Cannot perform search: API limit reached. Please check back next month.")
            return
        if not google_key:
            st.error("🔑 **Google Maps API Key** is missing. Paste your key in the sidebar.")
            return

        # Reset state for new search
        st.session_state["all_results"] = []
        st.session_state["current_batch"] = []
        st.session_state["seen_ids"] = set()
        st.session_state["search_round"] = 0
        st.session_state["city_center"] = (0.0, 0.0)
        st.session_state["raw_cache"] = []
        st.session_state["city"] = city
        st.session_state["category"] = category

        log_search(city, category)
        _run_search_round(google_key, category, city)
        st.session_state["search_round"] = 1

    # ------------------------------------------------------------------
    # Handle Filter action
    # ------------------------------------------------------------------
    if filter_clicked:
        df_to_filter = None
        if filter_source == "Current Batch":
            if st.session_state.get("current_batch"):
                df_to_filter = pd.DataFrame(st.session_state["current_batch"])
            else:
                st.sidebar.warning("Current batch is empty.")
        elif filter_source == "All Searches":
            if st.session_state.get("all_results"):
                df_to_filter = pd.DataFrame(st.session_state["all_results"])
            else:
                st.sidebar.warning("No search results to filter.")
        elif filter_source == "Upload CSV":
            if uploaded_csv is not None:
                try:
                    df_to_filter = pd.read_csv(uploaded_csv)
                except Exception as e:
                    st.sidebar.error(f"Error reading CSV: {e}")
            else:
                st.sidebar.warning("Please upload a CSV file.")
                
        if df_to_filter is not None and not df_to_filter.empty:
            if "Website URL" not in df_to_filter.columns:
                st.sidebar.error("Data must have a 'Website URL' column.")
            else:
                info_msg = st.empty()
                info_msg.info("Filtering departments... This may take a while as it visits each website.")
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total = len(df_to_filter)
                departments_found = []
                for i, url in enumerate(df_to_filter['Website URL']):
                    status_text.text(f"Checking {i+1}/{total}...")
                    departments_found.append(check_departments(url))
                    progress_bar.progress((i + 1) / total)
                    
                status_text.empty()
                progress_bar.empty()
                info_msg.empty()
                
                df_to_filter['Departments Found'] = departments_found
                st.session_state["filtered_df"] = df_to_filter
                st.sidebar.success("Filtering complete!")

    # ------------------------------------------------------------------
    # Display results
    # ------------------------------------------------------------------
    all_results = st.session_state.get("all_results", [])
    current_batch = st.session_state.get("current_batch", [])
    searched_city = st.session_state.get("city", "")
    searched_category = st.session_state.get("category", "")

    if all_results:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        # Stats
        avg_rating = 0
        rated_count = 0
        total_reviews = 0
        for h in all_results:
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
        rounds = st.session_state.get("search_round", 1)

        st.markdown(
            f"""
            <div class="metric-row">
                <div class="metric-card">
                    <div class="value">{len(all_results)}</div>
                    <div class="label">Total Results</div>
                </div>
                <div class="metric-card">
                    <div class="value">{len(current_batch)}</div>
                    <div class="label">Latest Batch</div>
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
                    <div class="value">{rounds}</div>
                    <div class="label">Searches Done</div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )

        df = pd.DataFrame(all_results)
        display_cols = ["Name", "City", "Address", "Phone", "Website URL", "Rating", "Reviews"]
        df_display = df[[c for c in display_cols if c in df.columns]]
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=min(len(df_display)*38+50, 600))

        # ------ Load More button ------
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        round_idx = st.session_state.get("search_round", 1)
        can_load_more = round_idx <= len(SEARCH_OFFSETS)

        if can_load_more:
            load_more = st.button(
                f"➕  Load More Results (round {round_idx + 1} of {len(SEARCH_OFFSETS) + 1})",
                use_container_width=True,
                key="load_more",
            )
            if load_more:
                if not google_key:
                    st.error("🔑 Paste your Google Maps API Key in the sidebar.")
                else:
                    lat, lng = st.session_state["city_center"]
                    dlat, dlng = SEARCH_OFFSETS[round_idx - 1]
                    biased_loc = f"{lat + dlat},{lng + dlng}"
                    _run_search_round(
                        google_key,
                        searched_category,
                        searched_city,
                        location=biased_loc,
                        radius=10000,
                    )
                    st.session_state["search_round"] = round_idx + 1
                    st.rerun()
        else:
            st.info("🏁 All 16 search directions exhausted for this city.")

        # ------ Download buttons ------
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        def _strip_pid(records):
            return [{k: v for k, v in h.items() if k != "place_id"} for h in records]

        safe_city = searched_city.split(",")[0].strip().lower().replace(" ", "_")
        safe_cat = searched_category.strip().lower().replace(" ", "_")
        base_filename = f"{safe_city}_{safe_cat}"

        st.markdown("##### 📥 Download Current Batch")
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            st.download_button(
                "CSV (current)",
                data=to_csv_bytes(_strip_pid(current_batch)),
                file_name=f"{base_filename}_current.csv",
                mime="text/csv",
                use_container_width=True,
                on_click=log_download_callback,
                args=(searched_city, searched_category),
            )
        with c2:
            st.download_button(
                "JSON (current)",
                data=to_json_bytes(_strip_pid(current_batch)),
                file_name=f"{base_filename}_current.json",
                mime="application/json",
                use_container_width=True,
                on_click=log_download_callback,
                args=(searched_city, searched_category),
            )

        if len(all_results) > len(current_batch):
            st.markdown("##### 📥 Download All Searches (merged)")
            a1, a2, _ = st.columns([1, 1, 3])
            with a1:
                st.download_button(
                    f"CSV (all {len(all_results)})",
                    data=to_csv_bytes(_strip_pid(all_results)),
                    file_name=f"{base_filename}_all.csv",
                    mime="text/csv",
                    use_container_width=True,
                    on_click=log_download_callback,
                    args=(searched_city, searched_category),
                )
            with a2:
                st.download_button(
                    f"JSON (all {len(all_results)})",
                    data=to_json_bytes(_strip_pid(all_results)),
                    file_name=f"{base_filename}_all.json",
                    mime="application/json",
                    use_container_width=True,
                    on_click=log_download_callback,
                    args=(searched_city, searched_category),
                )

    filtered_df = st.session_state.get("filtered_df")
    if filtered_df is not None:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("### 🏥 Filtered Department Results")
        
        display_cols_filtered = ["Name", "City", "Address", "Phone", "Website URL", "Rating", "Reviews", "Departments Found"]
        df_filtered_display = filtered_df[[c for c in display_cols_filtered if c in filtered_df.columns]]
        st.dataframe(df_filtered_display, use_container_width=True, hide_index=True)
        
        st.markdown("##### 📥 Download Filtered Results")
        c1, c2, _ = st.columns([1, 1, 3])
        
        base_filename = "filtered_departments"
        # determine base filename gracefully
        if filter_source == "Upload CSV" and uploaded_csv is not None:
            base_filename = f"filtered_{uploaded_csv.name.split('.')[0]}"
        elif searched_city and searched_category:
            safe_city = searched_city.split(",")[0].strip().lower().replace(" ", "_")
            safe_cat = searched_category.strip().lower().replace(" ", "_")
            base_filename = f"filtered_{safe_city}_{safe_cat}"
            
        with c1:
            st.download_button(
                "CSV (Filtered)",
                data=filtered_df.drop(columns=['place_id'], errors='ignore').to_csv(index=False).encode('utf-8'),
                file_name=f"{base_filename}.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_filtered_csv",
                on_click=log_download_callback,
                args=(searched_city, searched_category)
            )
        with c2:
            st.download_button(
                "JSON (Filtered)",
                data=filtered_df.drop(columns=['place_id'], errors='ignore').to_json(orient="records", indent=2).encode('utf-8'),
                file_name=f"{base_filename}.json",
                mime="application/json",
                use_container_width=True,
                key="dl_filtered_json",
                on_click=log_download_callback,
                args=(searched_city, searched_category)
            )

    st.markdown('<div class="footer">MedMap · Built with Streamlit & Google Maps Places API</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
