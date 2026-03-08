# 📍 MedMap

**MedMap** is a fast, interactive Streamlit web application that retrieves place data using the **Google Maps Places API (New)** & **Geocoding API**. It utilizes a dynamic 3x3 geographic grid search to bypass Google's result limits, discovering hundreds of unique places (hospitals, pharmacies, clinics, etc.) in any given city, with easy exports to CSV and JSON formats.

It features a permanent **Supabase** backend to automatically log search history, download history, monitor active sessions, and dynamically track Google API credit usage across Streamlit Community Cloud reboots.

---

## ✨ Features

- **🔍 Generic Search**: Search for *any* place category (not just hospitals) in any city worldwide.
- **🗺️ Geographic Grid Search**: Automatically geocodes your target city and launches a 3x3 radius search algorithm to extract 150+ unique places per query.
- **🛡️ Deduplication & Strict Filtering**: Removes duplicates automatically and strictly validates that results belong inside the target city limits.
- **🌐 Efficient Data Extraction**: Fetches details, ratings, international phone numbers, and official websites in a single, optimized request using FieldMasks.
- **📈 API Usage Dashboard**: Built-in monitoring connects to Supabase to calculate your monthly Google Maps API usage in real-time, warning you at 70% and dynamically blocking requests at 1000/month to guarantee you remain within the free tier.
- **🗃️ Persistent Cloud History**: Uses `supabase-py` so your search logs, download history, and session tracking survive ephemeral Streamlit Cloud container reboots.

---

## 🚀 Setup & Usage (Local)

### 1. Prerequisites

- Python 3.9+
- A [Google Cloud Console](https://console.cloud.google.com/apis/credentials) project with the **Places API (New)** AND **Geocoding API** enabled.
- A free [Supabase](https://supabase.com/) project (with the Data API enabled).

### 2. Install Dependencies

```bash
# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 3. Setup Environment Variables

Create a local `.env` file in the root directory (do not commit this to GitHub) and add your keys:

```env
GOOGLE_MAPS_API_KEY="your_google_key"
SUPABASE_URL="https://your_project.supabase.co"
SUPABASE_KEY="your_public_anon_key"
```

### 4. Run the App

```bash
streamlit run app.py
```

The application will open in your default web browser (usually at `http://localhost:8501`).

---

## 📦 Project Structure

```text
medmap/
├── app.py                # Main Streamlit application with Supabase integration
├── requirements.txt      # Python dependencies (streamlit, requests, pandas, supabase, httpx)
└── README.md             # This document
```

---

## 🌍 Export Format

The dynamically generated CSV/JSON exports (e.g., `kochi_pharmacy.csv`) will always contain:

- `Name`
- `City`
- `Address`
- `Phone` (International/National)
- `Website URL`
- `Rating`
- `Reviews`

---

## 🛠️ Deploying to Streamlit Community Cloud

MedMap is designed to securely run 24/7 on Streamlit Cloud:

1. Push this repository to GitHub. Ensure `.env` is omitted.
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your GitHub account.
3. Select your repository and launch `app.py`.
4. **CRITICAL:** Before deploying, navigate to **Advanced Settings -> Secrets** and paste your production keys:

```toml
GOOGLE_MAPS_API_KEY="AIzaSy..."
SUPABASE_URL="https://your_project.supabase.co"
SUPABASE_KEY="sb_publishable_..."
```
5. Click **Deploy**. Your Dashboard and History panels will remain perfectly synchronized with Supabase moving forward!
