# MedMap 📍

![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat&logo=Streamlit&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=flat&logo=supabase&logoColor=white)
![Google Maps API](https://img.shields.io/badge/Google_Maps_API-4285F4?style=flat&logo=googlemaps&logoColor=white)

**MedMap** is an enterprise-grade Streamlit web application engineered to extract, deduplicate, and export location data using the **Google Maps Places (New)** and **Geocoding APIs**. 

Designed to bypass conventional API pagination constraints, MedMap utilizes a dynamic 3x3 geographic grid-search algorithm to retrieve hundreds of unique points-of-interest (POIs) per query. It features a decentralized, persistent **Supabase** backend for telemetry, quota monitoring, and session state management across ephemeral cloud environments.

---

## 📑 Table of Contents
1. [Core Architecture](#core-architecture)
2. [Features](#features)
3. [Prerequisites](#prerequisites)
4. [Local Installation](#local-installation)
5. [Configuration](#configuration)
6. [Cloud Deployment](#cloud-deployment)

---

## 🏗️ Core Architecture

- **Frontend**: Streamlit (Python)
- **Data Layer**: Pandas (Vectorized cleaning & export caching)
- **Database**: Supabase PostgreSQL (REST API wrapper via `supabase-py`)
- **External Services**: Google Cloud Platform (Places API New, Geocoding API)
- **State Management**: `st.session_state` paired with UUID-based browser fingerprinting

---

## ✨ Features

- **Unrestricted Grid Searching**: Translates a standard query into a coordinate map, dispatching 9 concurrent geographic boundary searches to circumvent Google's 60-result pagination hard-limit.
- **Quota Telemetry & Safeguards**: Connects to Supabase to calculate executing API calls dynamically. Enforces strict kill-switches at 100% quota to prevent accidental billing overages on Google Cloud.
- **Strict Boundary Validation**: Evaluates reverse-geocoded addresses in real-time to drop results that belong to neighboring jurisdictions or fuzzy-matched localities.
- **Optimized FieldMasking**: Restricts Google Places queries strictly to `displayName`, `formattedAddress`, `rating`, `userRatingCount`, `websiteUri`, and `nationalPhoneNumber` to minimize byte-load and API expenses.
- **Stateless Persistence**: Search history, active browser sessions, and dataset downloads are logged irreversibly to Supabase, immune to Streamlit Community Cloud server recycling.

---

## 🔒 Prerequisites

To run MedMap, you must provision the following cloud resources:

1. **Google Cloud Console**
   - Enable **Places API (New)**
   - Enable **Geocoding API**
   - Generate a single restricted API Key

2. **Supabase**
   - Create a free PostgreSQL project
   - Enable the Data API
   - Ensure tables exist for `search_history`, `downloads`, `api_usage`, and `user_sessions` (See SQL deployment script).

---

## 💻 Local Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/medmap.git
   cd medmap
   ```

2. **Initialize a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## ⚙️ Configuration

MedMap utilizes environment variables for zero-trust security. Create a `.env` file in the root directory:

```env
GOOGLE_MAPS_API_KEY="AIzaSy_YOUR_GOOGLE_KEY..."
SUPABASE_URL="https://your_project.supabase.co"
SUPABASE_KEY="sb_publishable_YOUR_ANON_KEY..."
```

*(Note: `.env` is explicitly declared in `.gitignore` and will not be committed to version control).*

---

## ☁️ Cloud Deployment (Streamlit Community Cloud)

MedMap is architected to run seamlessly on [Streamlit Community Cloud](https://share.streamlit.io).

1. Push your local `main` branch to GitHub.
2. Link the repository to your Streamlit Workspace.
3. Before spinning up the instance, configure your **Advanced Secrets**:

```toml
GOOGLE_MAPS_API_KEY="AIzaSy_YOUR_GOOGLE_KEY..."
SUPABASE_URL="https://your_project.supabase.co"
SUPABASE_KEY="sb_publishable_YOUR_ANON_KEY..."
```

4. Click **Deploy**. Telemetry and history will synchronize automatically with your Supabase backend.

---
*Built with ❤️ utilizing Python & Streamlit.*
