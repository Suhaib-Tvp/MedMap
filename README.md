# 🏥 MedMap

**MedMap** is a fast, interactive Streamlit web application that retrieves hospital data from the **Google Maps Places API** for any given city. It allows location-biased searching to discover hundreds of unique hospitals, with easy exports to CSV and JSON formats.

---

## ✨ Features

- **🔍 Interactive UI**: Beautiful, premium Streamlit interface.
- **📄 Automatic Pagination**: Fetches up to 60 results per batch seamlessly.
- **➕ Load More**: Intelligently shifts the search radius iteratively across 16 compass directions to discover hospitals that Google Maps hides behind its 60-result hard limit.
- **🛡️ Deduplication**: Automatically removes duplicate entries across search rounds.
- **🌐 Website Retrieval**: Specifically fetches the official website for each hospital via the Place Details API.
- **📊 Export Options**: Download your current search batch, or download a merged file containing all accumulated searches in both CSV and JSON.
- **🔒 Secure**: API keys are entered directly into the browser session via the UI and are never saved to disk. Safe for GitHub and public deployment.

---

## 🚀 Setup & Usage (Local)

### 1. Prerequisites

- Python 3.9+
- A [Google Maps API key](https://console.cloud.google.com/apis/credentials) with the **Places API** enabled.

### 2. Install Dependencies

```bash
# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 3. Run the App

Instead of configuring `.env` files, simply launch the app directly:

```bash
streamlit run app.py
```

The application will open in your default web browser (usually at `http://localhost:8501`).

### 4. How to Use

1. **Enter API Key**: Paste your Google Maps API Key into the sidebar's password field.
2. **Search**: Enter a city name (e.g., "Hyderabad, India") and click **Search Hospitals**.
3. **Load More**: To discover hospitals beyond the initial 60, click the **Load More Hospitals** button at the bottom of the table.
4. **Download**: Use the download buttons to export your data to CSV or JSON.

---

## 📦 Project Structure

```text
medmap/
├── app.py                # Main Streamlit application
├── requirements.txt      # Python dependencies (streamlit, requests, pandas)
└── README.md             # This file
```

---

## 🌍 Export Format

The generated CSV and JSON files will contain the following columns/keys:

- `Hospital Name`
- `City`
- `State`
- `Address`
- `Website URL`
- `Rating`
- `Reviews`

---

Since API keys are supplied via the UI by the end user at runtime, you do **not** need to configure Streamlit Secrets.
