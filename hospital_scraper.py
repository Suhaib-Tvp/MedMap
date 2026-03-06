#!/usr/bin/env python3
"""
Hospital Data Retrieval Script
===============================
Fetches hospital details from Google Maps Places API for a given city,
optionally cleans addresses with Groq LLM, and saves results to CSV & JSON.

Usage:
    python hospital_scraper.py                          # Default: Hyderabad, India
    python hospital_scraper.py --city "Chennai, India"  # Different city
    python hospital_scraper.py --clean-addresses        # Enable Groq address cleaning
    python hospital_scraper.py --dry-run                # Validate setup without API calls
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging configuration
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
PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
# Google returns at most 20 results per page, up to 3 pages (60 results).
MAX_PAGES = 3
# Google requires a short delay before requesting the next page token.
PAGE_TOKEN_DELAY_SECONDS = 2
# Default output file names (without extension).
DEFAULT_OUTPUT_BASENAME = "hospitals"


# ============================================================================
# 1. Google Maps Places API helpers
# ============================================================================

def search_hospitals(
    api_key: str,
    query: str,
    page_token: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Execute a single Places Text Search request.

    Args:
        api_key:    Google Maps API key.
        query:      Free-text search query, e.g. "hospitals in Hyderabad, India".
        page_token: Token for the next page of results (None for the first page).

    Returns:
        A tuple of (results_list, next_page_token).
        next_page_token is None when there are no more pages.

    Raises:
        requests.HTTPError: On non-2xx HTTP status codes.
        ValueError:         When the API returns a non-OK status.
    """
    params: Dict[str, str] = {
        "query": query,
        "key": api_key,
    }
    if page_token:
        params["pagetoken"] = page_token

    logger.info("Sending Places API request (page_token=%s)…", bool(page_token))
    response = requests.get(PLACES_TEXT_SEARCH_URL, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    status = data.get("status", "UNKNOWN")

    if status == "ZERO_RESULTS":
        logger.warning("No results returned by the API.")
        return [], None

    if status not in ("OK",):
        error_msg = data.get("error_message", "No error message provided.")
        raise ValueError(
            f"Places API returned status '{status}': {error_msg}"
        )

    results = data.get("results", [])
    next_token = data.get("next_page_token")

    logger.info("Received %d results.", len(results))
    return results, next_token


def fetch_all_hospitals(api_key: str, city: str) -> List[Dict[str, Any]]:
    """
    Fetch all hospital results for *city*, handling pagination automatically.

    Args:
        api_key: Google Maps API key.
        city:    Target city string, e.g. "Hyderabad, India".

    Returns:
        Combined list of raw place result dicts across all pages.
    """
    query = f"hospitals in {city}"
    all_results: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    for page_num in range(1, MAX_PAGES + 1):
        try:
            results, page_token = search_hospitals(api_key, query, page_token)
            all_results.extend(results)
            logger.info(
                "Page %d fetched — running total: %d hospitals.",
                page_num,
                len(all_results),
            )

            if not page_token:
                logger.info("No more pages available.")
                break

            # Google needs a short delay before the next page token becomes valid.
            logger.info(
                "Waiting %ds for next page token…", PAGE_TOKEN_DELAY_SECONDS
            )
            time.sleep(PAGE_TOKEN_DELAY_SECONDS)

        except requests.exceptions.HTTPError as exc:
            logger.error("HTTP error on page %d: %s", page_num, exc)
            if exc.response is not None and exc.response.status_code == 429:
                logger.error("Rate limit hit. Try again later or check your quota.")
            break
        except ValueError as exc:
            logger.error("API error on page %d: %s", page_num, exc)
            break
        except requests.exceptions.RequestException as exc:
            logger.error("Network error on page %d: %s", page_num, exc)
            break

    logger.info("Total hospitals fetched: %d", len(all_results))
    return all_results


# ============================================================================
# 2. Data extraction
# ============================================================================

def extract_hospital_details(
    place: Dict[str, Any],
    default_city: str = "",
    default_state: str = "",
) -> Dict[str, str]:
    """
    Extract structured fields from a raw Places API result.

    The API does not always provide separate city/state fields, so we attempt
    to parse them from `address_components` (via Place Details) or fall back
    to the `formatted_address`.

    Args:
        place:         A single result dict from the Places API.
        default_city:  Fallback city if not found in the result.
        default_state: Fallback state if not found in the result.

    Returns:
        Dict with keys: hospital_name, city, state, full_address, latitude,
        longitude, rating, user_ratings_total, place_id.
    """
    name = place.get("name", "N/A")
    address = place.get("formatted_address", "N/A")

    # Attempt to parse city and state from formatted_address.
    # Typical format: "..., City, State ZIP, Country"
    city = default_city
    state = default_state
    address_parts = [p.strip() for p in address.split(",")]
    if len(address_parts) >= 3:
        # Second-to-last part often contains state + postal code.
        state_candidate = address_parts[-2].strip()
        # Remove trailing digits (postal code).
        state_parsed = "".join(
            ch for ch in state_candidate if not ch.isdigit()
        ).strip()
        if state_parsed:
            state = state_parsed

        # Third-to-last part is usually the city.
        city = address_parts[-3].strip()

    # Geo-coordinates (useful metadata).
    location = place.get("geometry", {}).get("location", {})
    lat = location.get("lat", "")
    lng = location.get("lng", "")

    return {
        "hospital_name": name,
        "city": city,
        "state": state,
        "full_address": address,
        "latitude": str(lat),
        "longitude": str(lng),
        "rating": str(place.get("rating", "")),
        "user_ratings_total": str(place.get("user_ratings_total", "")),
        "place_id": place.get("place_id", ""),
    }


# ============================================================================
# 3. Groq LLM address cleaning (optional)
# ============================================================================

def clean_address_with_groq(
    groq_client: Any,
    hospital: Dict[str, str],
) -> Dict[str, str]:
    """
    Use Groq LLM to normalize/structure the address and fill missing city/state.

    Args:
        groq_client: An initialized ``groq.Groq`` client instance.
        hospital:    A hospital dict produced by ``extract_hospital_details``.

    Returns:
        Updated hospital dict with cleaned fields.
    """
    prompt = (
        "You are a data-cleaning assistant. Given the following hospital record, "
        "return a JSON object with exactly these keys: "
        "hospital_name, city, state, full_address. "
        "Clean up the address, fix any obvious typos, and ensure city and state "
        "are correctly extracted. Respond ONLY with valid JSON, no extra text.\n\n"
        f"Input:\n"
        f"  hospital_name: {hospital['hospital_name']}\n"
        f"  full_address:  {hospital['full_address']}\n"
        f"  city:          {hospital['city']}\n"
        f"  state:         {hospital['state']}\n"
    )

    try:
        chat_completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=300,
        )
        raw_response = chat_completion.choices[0].message.content.strip()

        # Strip markdown fences if present.
        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            raw_response = "\n".join(lines[1:-1])

        cleaned = json.loads(raw_response)

        # Merge cleaned fields back, keeping original extras (lat, lng, etc.).
        for key in ("hospital_name", "city", "state", "full_address"):
            if key in cleaned and cleaned[key]:
                hospital[key] = cleaned[key]

        logger.debug("Groq cleaned: %s", hospital["hospital_name"])

    except json.JSONDecodeError:
        logger.warning(
            "Groq returned invalid JSON for '%s'. Keeping original.",
            hospital["hospital_name"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Groq error for '%s': %s. Keeping original.",
            hospital["hospital_name"],
            exc,
        )

    return hospital


def clean_all_addresses(hospitals: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Batch-clean addresses using Groq. Initializes the Groq client once.

    Returns:
        The same list with cleaned fields where possible.
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logger.error("GROQ_API_KEY not set. Skipping address cleaning.")
        return hospitals

    try:
        from groq import Groq  # Import here so groq is optional at module level.

        client = Groq(api_key=groq_api_key)
    except ImportError:
        logger.error(
            "groq package not installed. Run: pip install groq"
        )
        return hospitals

    logger.info("Cleaning %d addresses via Groq LLM…", len(hospitals))
    cleaned: List[Dict[str, str]] = []
    for i, h in enumerate(hospitals, 1):
        cleaned.append(clean_address_with_groq(client, h))
        if i % 10 == 0:
            logger.info("  …cleaned %d / %d", i, len(hospitals))
        # Small delay to avoid Groq rate limits.
        time.sleep(0.5)

    logger.info("Address cleaning complete.")
    return cleaned


# ============================================================================
# 4. Output helpers
# ============================================================================

def _fallback_output_path(filepath: str) -> str:
    """Return a timestamped fallback path beside the requested file."""
    base, ext = os.path.splitext(filepath)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base}_{timestamp}{ext}"

def save_to_csv(hospitals: List[Dict[str, str]], filepath: str) -> None:
    """Write hospital records to a CSV file."""
    if not hospitals:
        logger.warning("No data to save.")
        return

    fieldnames = list(hospitals[0].keys())
    target_path = filepath
    try:
        with open(target_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(hospitals)
    except PermissionError:
        target_path = _fallback_output_path(filepath)
        logger.warning(
            "Could not write to %s (file may be open/locked). Saving to %s instead.",
            filepath,
            target_path,
        )
        with open(target_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(hospitals)

    logger.info("Saved %d records to %s", len(hospitals), target_path)


def save_to_json(hospitals: List[Dict[str, str]], filepath: str) -> None:
    """Write hospital records to a pretty-printed JSON file."""
    if not hospitals:
        logger.warning("No data to save.")
        return

    target_path = filepath
    try:
        with open(target_path, "w", encoding="utf-8") as fh:
            json.dump(hospitals, fh, indent=2, ensure_ascii=False)
    except PermissionError:
        target_path = _fallback_output_path(filepath)
        logger.warning(
            "Could not write to %s (file may be open/locked). Saving to %s instead.",
            filepath,
            target_path,
        )
        with open(target_path, "w", encoding="utf-8") as fh:
            json.dump(hospitals, fh, indent=2, ensure_ascii=False)

    logger.info("Saved %d records to %s", len(hospitals), target_path)


# ============================================================================
# 5. CLI and main orchestration
# ============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch hospital details from Google Maps Places API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python hospital_scraper.py\n"
            "  python hospital_scraper.py --city 'Chennai, India'\n"
            "  python hospital_scraper.py --clean-addresses\n"
            "  python hospital_scraper.py --output results --city 'Mumbai, India'\n"
        ),
    )
    parser.add_argument(
        "--city",
        default="Hyderabad, India",
        help="Target city for hospital search (default: 'Hyderabad, India').",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_BASENAME,
        help=(
            "Base name for output files (default: 'hospitals'). "
            "Generates <name>.csv and <name>.json."
        ),
    )
    parser.add_argument(
        "--clean-addresses",
        action="store_true",
        help="Use Groq LLM to clean and structure addresses.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and exit without making API calls.",
    )
    return parser.parse_args()


def validate_environment(need_groq: bool = False) -> str:
    """
    Load .env and validate that required API keys are present.

    Args:
        need_groq: Whether the Groq key is also required.

    Returns:
        The Google Maps API key.

    Raises:
        SystemExit: If required keys are missing.
    """
    load_dotenv()

    google_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not google_key:
        logger.error(
            "GOOGLE_MAPS_API_KEY is not set. "
            "Copy .env.example to .env and add your key."
        )
        sys.exit(1)

    if need_groq and not os.getenv("GROQ_API_KEY"):
        logger.error(
            "GROQ_API_KEY is not set but --clean-addresses was requested. "
            "Add it to your .env file or remove the flag."
        )
        sys.exit(1)

    return google_key


def main() -> None:
    """Main entry point: parse args → fetch → extract → (clean) → save."""
    args = parse_args()

    logger.info("=" * 60)
    logger.info("Hospital Data Retrieval Script")
    logger.info("Target city : %s", args.city)
    logger.info("Output base : %s", args.output)
    logger.info("Clean addrs : %s", args.clean_addresses)
    logger.info("Dry run     : %s", args.dry_run)
    logger.info("=" * 60)

    # --- Step 1: Validate environment ---
    api_key = validate_environment(need_groq=args.clean_addresses)
    logger.info("✅ Environment validated — API key(s) present.")

    if args.dry_run:
        logger.info("Dry-run mode — exiting without API calls.")
        return

    # --- Step 2: Fetch raw results from Google Maps ---
    raw_results = fetch_all_hospitals(api_key, args.city)
    if not raw_results:
        logger.warning("No hospitals found. Exiting.")
        return

    # --- Step 3: Extract structured details ---
    # Derive default city/state from the --city argument.
    city_parts = [p.strip() for p in args.city.split(",")]
    default_city = city_parts[0] if city_parts else ""
    default_state = city_parts[1] if len(city_parts) > 1 else ""

    hospitals = [
        extract_hospital_details(place, default_city, default_state)
        for place in raw_results
    ]
    logger.info("Extracted details for %d hospitals.", len(hospitals))

    # --- Step 4: (Optional) Clean addresses with Groq ---
    if args.clean_addresses:
        hospitals = clean_all_addresses(hospitals)

    # --- Step 5: Save output ---
    output_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(output_dir, f"{args.output}.csv")
    json_path = os.path.join(output_dir, f"{args.output}.json")

    save_to_csv(hospitals, csv_path)
    save_to_json(hospitals, json_path)

    logger.info("🏁 Done! Files saved:")
    logger.info("   CSV  → %s", csv_path)
    logger.info("   JSON → %s", json_path)


if __name__ == "__main__":
    main()
