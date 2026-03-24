import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import time
import json
import os
import requests

# --- 1. CONFIGURATION ---
DAILY_GOAL = 70
LOCATION_ID = "snQISHLOuYGlR3jXbGU3"
GHL_API_KEY = os.environ.get('GHL_API_KEY')
GCP_JSON = os.environ.get('gcp_service_account') # Matching your lowercase Render key

def get_live_ghl_count():
    if not GHL_API_KEY: return 0
    # Strip any accidental characters from Render
    token = GHL_API_KEY.replace('{', '').replace('}', '').replace('"', '').replace("'", "").strip()
    
    now = datetime.now(timezone.utc)
    # Today starts at 9 AM ET (13:00 UTC)
    start_time = now.replace(hour=13, minute=0, second=0, microsecond=0)
    if now.hour < 13: start_time -= timedelta(days=1)

    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {"Authorization": f"Bearer {token}", "Version": "2021-04-15", "Content-Type": "application/json"}
    payload = {
        "locationId": LOCATION_ID,
        "filters": [{"field": "updatedAt", "operator": "gte", "value": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return sum(1 for c in r.json().get('contacts', []) if "client" in [t.lower() for t in c.get('tags', [])])
    except: return 0

# --- 2. THE UI (DRAW THIS FIRST TO STOP THE LOOP) ---
st.set_page_config(layout="wide")

# Get GHL Count
live_val = get_live_ghl_count()

# Display the big number immediately
st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; margin:0;">{live_val}</p>', unsafe_allow_html=True)

# --- 3. GOOGLE AUTH (WRAPPED IN SAFETY) ---
if GCP_JSON:
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        info = json.loads(GCP_JSON)
        if 'private_key' in info:
            info['private_key'] = info['private_key'].replace('\\n', '\n')
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
        gc = gspread.authorize(creds)
        st.success("Google Sheets Connected")
        # Add sheet reading logic here once the big number is stable
    except Exception as e:
        st.error(f"Google Auth Error: {e}")
else:
    st.error("Variable 'gcp_service_account' not found in Render.")

# --- 4. REFRESH ---
time.sleep(60)
st.rerun()
