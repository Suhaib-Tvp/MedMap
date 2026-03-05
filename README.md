# 🏥 Hospital Data Retrieval Script

Retrieve hospital details from **Google Maps Places API** for any city and save to CSV/JSON.  
Optionally clean & structure addresses using **Groq LLM**.

---

## Features

- 🔍 Search hospitals via Google Maps Text Search API
- 📄 Automatic **pagination** (up to 60 results)
- 🧠 Optional **Groq LLM** address cleaning (`--clean-addresses`)
- 📊 Output to both **CSV** and **JSON**
- 🌍 Easily extensible to **any city** via `--city` flag
- 🛡️ Robust error handling (rate limits, network errors, missing fields)

---

## Setup

### 1. Prerequisites

- Python 3.9+
- A [Google Maps API key](https://console.cloud.google.com/apis/credentials) with the **Places API** enabled
- *(Optional)* A [Groq API key](https://console.groq.com/keys) for address cleaning

### 2. Install dependencies

```bash
# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 3. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` and replace the placeholder values with your real keys:

```
GOOGLE_MAPS_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...          # only needed with --clean-addresses
```

> **⚠️ Security**: Never commit your `.env` file. Add it to `.gitignore`.

---

## Usage

```bash
# Default — fetch hospitals in Hyderabad, India
python hospital_scraper.py

# Different city
python hospital_scraper.py --city "Chennai, India"

# Custom output file name (creates results.csv & results.json)
python hospital_scraper.py --output results

# Enable Groq address cleaning
python hospital_scraper.py --clean-addresses

# Dry run — validate config without making API calls
python hospital_scraper.py --dry-run

# Combine flags
python hospital_scraper.py --city "Mumbai, India" --clean-addresses --output mumbai_hospitals
```

---

## Output Format

### CSV (`hospitals.csv`)

| hospital_name | city | state | full_address | latitude | longitude | rating | user_ratings_total | place_id |
|---|---|---|---|---|---|---|---|---|
| Apollo Hospital | Hyderabad | Telangana | Jubilee Hills, Hyderabad, Telangana 500033, India | 17.43 | 78.41 | 4.2 | 1500 | ChIJ... |

### JSON (`hospitals.json`)

```json
[
  {
    "hospital_name": "Apollo Hospital",
    "city": "Hyderabad",
    "state": "Telangana",
    "full_address": "Jubilee Hills, Hyderabad, Telangana 500033, India",
    "latitude": "17.43",
    "longitude": "78.41",
    "rating": "4.2",
    "user_ratings_total": "1500",
    "place_id": "ChIJ..."
  }
]
```

---

## Project Structure

```
hospital/
├── .env.example          # API key template
├── .env                  # Your actual keys (git-ignored)
├── requirements.txt      # Python dependencies
├── hospital_scraper.py   # Main script
├── hospitals.csv         # Generated output
├── hospitals.json        # Generated output
└── README.md             # This file
```

---

## Extending to Other Cities

Simply pass a different `--city` value:

```bash
python hospital_scraper.py --city "Bangalore, India" --output bangalore_hospitals
python hospital_scraper.py --city "New York, USA"    --output nyc_hospitals
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `GOOGLE_MAPS_API_KEY is not set` | Copy `.env.example` → `.env` and add your key |
| `REQUEST_DENIED` | Enable the **Places API** in your Google Cloud Console |
| `OVER_QUERY_LIMIT` | You've hit your daily quota — wait or upgrade your plan |
| `groq package not installed` | Run `pip install groq` |
