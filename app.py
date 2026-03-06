#!/usr/bin/env python3
"""
Hospital Finder — Streamlit App
================================
Interactive web interface for retrieving hospital data from Google Maps
Places API.

Run:
    streamlit run app.py
"""

import csv
import io
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PLACES_TEXT_SEARCH_URL = (
    "https://places.googleapis.com/v1/places:searchText"
)
MAX_PAGES = 3
PAGE_TOKEN_DELAY_SECONDS = 2

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
# Page config — must be first Streamlit call
# ============================================================================
st.set_page_config(
    page_title="Hospital Finder",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# Custom CSS for a polished, premium look
# ============================================================================
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
# Google Maps Places API — Text Search
# ============================================================================

def _search_hospitals_page(
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
            "places.websiteUri,"
            "nextPageToken"
        ),
    }
    payload: Dict[str, Any] = {
        "textQuery": query,
    }
    if page_token:
        payload["pageToken"] = page_token
    if location and radius:
        lat_str, lng_str = location.split(",")
        payload["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": float(lat_str),
                    "longitude": float(lng_str)
                },
                "radius": float(radius)
            }
        }

    resp = requests.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=payload, timeout=30)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise ValueError(f"Places API returned an error: {exc.response.text}")

    data = resp.json()
    return data.get("places", []), data.get("nextPageToken")


def fetch_all_hospitals(
    api_key: str,
    city: str,
    location: Optional[str] = None,
    radius: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch all hospital results for *city* with automatic pagination.
    Optionally biased toward a specific location + radius.
    """
    query = f"hospitals in {city}"
    all_results: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    progress_bar = st.progress(0, text="Fetching page 1 …")

    for page_num in range(1, MAX_PAGES + 1):
        try:
            results, page_token = _search_hospitals_page(
                api_key, query, page_token, location, radius
            )
            all_results.extend(results)
            progress_bar.progress(
                page_num / MAX_PAGES,
                text=f"Fetched page {page_num} — {len(all_results)} hospitals so far",
            )

            if not page_token:
                break

            # Google requires a short delay before the next token is valid.
            time.sleep(PAGE_TOKEN_DELAY_SECONDS)

        except (requests.HTTPError, ValueError, requests.RequestException) as exc:
            logger.error("Error on page %d: %s", page_num, exc)
            st.warning(f"⚠️ Error fetching page {page_num}: {exc}")
            break

    progress_bar.empty()
    return all_results


def compute_centroid(hospitals: List[Dict[str, Any]]) -> Tuple[float, float]:
    """Return the average (lat, lng) from a list of raw place results."""
    lats, lngs = [], []
    for p in hospitals:
        loc = p.get("location", {})
        if "latitude" in loc and "longitude" in loc:
            lats.append(loc["latitude"])
            lngs.append(loc["longitude"])
    if not lats:
        return 0.0, 0.0
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


# ============================================================================
# Data extraction
# ============================================================================

def extract_hospital_details(
    place: Dict[str, Any],
    default_city: str = "",
    default_state: str = "",
) -> Dict[str, str]:
    """Parse raw Places result into a flat record dict."""
    name_dict = place.get("displayName", {})
    name = name_dict.get("text", "N/A") if isinstance(name_dict, dict) else "N/A"
    
    address = place.get("formattedAddress", "N/A")

    # Attempt city / state from formattedAddress.
    city = default_city
    state = default_state
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        state_candidate = "".join(
            ch for ch in parts[-2] if not ch.isdigit()
        ).strip()
        if state_candidate:
            state = state_candidate
        city = parts[-3].strip()

    return {
        "Hospital Name": name,
        "City": city,
        "State": state,
        "Address": address,
        "Website URL": place.get("websiteUri", ""),
        "Rating": str(place.get("rating", "")),
        "Reviews": str(place.get("userRatingCount", "")),
        "place_id": place.get("id", ""),
    }



# ============================================================================
# Conversion helpers for downloads
# ============================================================================

def to_csv_bytes(hospitals: List[Dict[str, str]]) -> bytes:
    """Convert hospital list to CSV bytes for download."""
    if not hospitals:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=hospitals[0].keys())
    writer.writeheader()
    writer.writerows(hospitals)
    return buf.getvalue().encode("utf-8")


def to_json_bytes(hospitals: List[Dict[str, str]]) -> bytes:
    """Convert hospital list to pretty JSON bytes for download."""
    return json.dumps(hospitals, indent=2, ensure_ascii=False).encode("utf-8")


# ============================================================================
# Main UI
# ============================================================================

def main() -> None:
    # ---- Initialise session state ----
    if "all_hospitals" not in st.session_state:
        st.session_state["all_hospitals"] = []        # accumulated across all rounds
    if "current_hospitals" not in st.session_state:
        st.session_state["current_hospitals"] = []    # latest batch only
    if "seen_ids" not in st.session_state:
        st.session_state["seen_ids"] = set()          # place_ids already stored
    if "search_round" not in st.session_state:
        st.session_state["search_round"] = 0          # 0 = first search
    if "city_center" not in st.session_state:
        st.session_state["city_center"] = (0.0, 0.0)
    if "raw_cache" not in st.session_state:
        st.session_state["raw_cache"] = []             # raw results for centroid

    # ---- Hero header ----
    st.markdown('<h1 class="hero-title">🏥 Hospital Finder</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-sub">Discover hospitals in any city — powered by Google Maps</p>',
        unsafe_allow_html=True,
    )

    # ---- Sidebar ----
    with st.sidebar:
        st.markdown("## 🔑 API Key")
        st.markdown("---")

        google_key = st.text_input(
            "Google Maps API Key",
            type="password",
            help="Get yours at https://console.cloud.google.com/apis/credentials",
        )

        st.markdown("---")
        st.markdown("## ⚙️ Search Settings")

        city = st.text_input(
            "🌍 City Name",
            value="Hyderabad, India",
            placeholder="e.g. Chennai, India",
        )

        st.markdown("---")
        search_clicked = st.button("🔍  Search Hospitals", use_container_width=True)

        st.markdown("---")
        st.markdown(
            "<div style='color:#55556e;font-size:0.75rem;text-align:center;'>"
            "Data via Google Maps Places API</div>",
            unsafe_allow_html=True,
        )

    # ------------------------------------------------------------------
    # Helper: run one search round, deduplicate, and append to state
    # ------------------------------------------------------------------
    def _run_search_round(
        google_key: str,
        city: str,
        location: Optional[str] = None,
        radius: Optional[int] = None,
    ) -> None:
        """Fetch a batch, deduplicate, enrich, and store in session state."""
        with st.spinner("Searching Google Maps …"):
            raw_results = fetch_all_hospitals(google_key, city, location, radius)

        # Filter out duplicates
        new_results = [
            r for r in raw_results
            if r.get("id") and r["id"] not in st.session_state["seen_ids"]
        ]

        if not new_results:
            st.warning("😕 No new hospitals found. You may have exhausted the area.")
            return

        # Parse city defaults
        city_parts = [p.strip() for p in city.split(",")]
        default_city = city_parts[0] if city_parts else ""
        default_state = city_parts[1] if len(city_parts) > 1 else ""

        # Extract details
        batch: List[Dict[str, str]] = []
        details_progress = st.progress(0, text="Extracting hospital details …")
        total = len(new_results)

        for i, place in enumerate(new_results, 1):
            batch.append(
                extract_hospital_details(place, default_city, default_state)
            )
            details_progress.progress(
                i / total,
                text=f"Processed {i} / {total} hospitals",
            )

        details_progress.empty()


        # Update session state
        for h in batch:
            st.session_state["seen_ids"].add(h["place_id"])
        st.session_state["current_hospitals"] = batch
        st.session_state["all_hospitals"].extend(batch)

        # Store raw results for centroid calculation
        st.session_state["raw_cache"].extend(new_results)
        st.session_state["city_center"] = compute_centroid(
            st.session_state["raw_cache"]
        )

    # ------------------------------------------------------------------
    # "Search Hospitals" button action — fresh search, resets state
    # ------------------------------------------------------------------
    if search_clicked:
        if not google_key:
            st.error(
                "🔑 **Google Maps API Key** is missing.  \n"
                "Paste your key in the sidebar to get started."
            )
            return

        # Reset state for a new fresh search
        st.session_state["all_hospitals"] = []
        st.session_state["current_hospitals"] = []
        st.session_state["seen_ids"] = set()
        st.session_state["search_round"] = 0
        st.session_state["city_center"] = (0.0, 0.0)
        st.session_state["raw_cache"] = []
        st.session_state["city"] = city

        _run_search_round(google_key, city)
        st.session_state["search_round"] = 1

    # ------------------------------------------------------------------
    # Display results
    # ------------------------------------------------------------------
    all_hospitals = st.session_state.get("all_hospitals", [])
    current_hospitals = st.session_state.get("current_hospitals", [])
    searched_city = st.session_state.get("city", "")

    if all_hospitals:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        # Metrics row (for ALL accumulated hospitals)
        avg_rating = 0
        rated_count = 0
        total_reviews = 0
        with_website = sum(1 for h in all_hospitals if h.get("Website URL"))
        for h in all_hospitals:
            try:
                r = float(h["Rating"])
                avg_rating += r
                rated_count += 1
            except (ValueError, KeyError):
                pass
            try:
                total_reviews += int(h["Reviews"])
            except (ValueError, KeyError):
                pass
        avg_rating = round(avg_rating / rated_count, 1) if rated_count else 0
        rounds = st.session_state.get("search_round", 1)

        st.markdown(
            f"""
            <div class="metric-row">
                <div class="metric-card">
                    <div class="value">{len(all_hospitals)}</div>
                    <div class="label">Total Hospitals</div>
                </div>
                <div class="metric-card">
                    <div class="value">{len(current_hospitals)}</div>
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
            """,
            unsafe_allow_html=True,
        )

        # Results table — ALL accumulated hospitals
        import pandas as pd

        df = pd.DataFrame(all_hospitals)
        display_cols = [
            "Hospital Name", "City", "State", "Address",
            "Website URL", "Rating", "Reviews",
        ]
        df_display = df[[c for c in display_cols if c in df.columns]]

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            height=min(len(df_display) * 38 + 50, 600),
        )

        # ------ Load More button ------
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        round_idx = st.session_state.get("search_round", 1)
        can_load_more = round_idx <= len(SEARCH_OFFSETS)

        if can_load_more:
            load_more = st.button(
                f"➕  Load More Hospitals (round {round_idx + 1})",
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
                        searched_city,
                        location=biased_loc,
                        radius=10000,
                    )
                    st.session_state["search_round"] = round_idx + 1
                    st.rerun()
        else:
            st.info("🏁 All search directions exhausted for this city.")

        # ------ Download buttons ------
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        def _strip_pid(records: List[Dict[str, str]]) -> List[Dict[str, str]]:
            return [{k: v for k, v in h.items() if k != "place_id"} for h in records]

        st.markdown("##### 📥 Download Current Search")
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            st.download_button(
                label="CSV (current)",
                data=to_csv_bytes(_strip_pid(current_hospitals)),
                file_name="hospitals_current.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                label="JSON (current)",
                data=to_json_bytes(_strip_pid(current_hospitals)),
                file_name="hospitals_current.json",
                mime="application/json",
                use_container_width=True,
            )

        if len(all_hospitals) > len(current_hospitals):
            st.markdown("##### 📥 Download All Searches (merged)")
            a1, a2, _ = st.columns([1, 1, 3])
            with a1:
                st.download_button(
                    label=f"CSV (all {len(all_hospitals)})",
                    data=to_csv_bytes(_strip_pid(all_hospitals)),
                    file_name="hospitals_all.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with a2:
                st.download_button(
                    label=f"JSON (all {len(all_hospitals)})",
                    data=to_json_bytes(_strip_pid(all_hospitals)),
                    file_name="hospitals_all.json",
                    mime="application/json",
                    use_container_width=True,
                )

    # ---- Footer ----
    st.markdown(
        '<div class="footer">Hospital Finder · Built with Streamlit & Google Maps Places API</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
