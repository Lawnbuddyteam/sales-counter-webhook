import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import time
import json
import os
import requests
import base64

# --- 1. CONFIGURATION ---
DAILY_GOAL = 70
SHEET_NAME = "Sales_Counter" 
LOCATION_ID = "snQISHLOuYGlR3jXbGU3"

# Render Keys (Exactly as they appear in your list)
GHL_API_KEY = os.environ.get('GHL_API_KEY')
GCP_JSON = os.environ.get('gcp_service_account') # Note: lowercase as found in your list

# --- 2. GHL LIVE FETCH ---
def get_live_ghl_count():
    if not GHL_API_KEY:
        return 0
    
    # Clean the token
    token = GHL_API_KEY.replace('{', '').replace('}', '').replace('"', '').replace("'", "").strip()
    
    # Time Logic: Today starts at 9 AM ET (13:00 UTC)
    now = datetime.now(timezone.utc)
    if now.hour >= 13:
        start_time = now.replace(hour=13, minute=0, second=0, microsecond=0)
    else:
        start_time = (now - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)

    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {"Authorization": f"Bearer {token}", "Version": "2021-04-15", "Content-Type": "application/json"}
    payload = {
        "locationId": LOCATION_ID,
        "pageLimit": 100,
        "filters": [{"field": "updatedAt", "operator": "gte", "value": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        contacts = r.json().get('contacts', [])
        return sum(1 for c in contacts if "client" in [t.lower() for t in c.get('tags', [])])
    except:
        return 0

# --- 3. GOOGLE AUTH ---
@st.cache_resource
def get_client():
    if not GCP_JSON:
        return None
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        info = json.loads(GCP_JSON)
        if 'private_key' in info:
            info['private_key'] = info['private_key'].replace('\\n', '\n')
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
        return gspread.authorize(creds)
    except:
        return None

# --- 4. MAIN UI ---
st.set_page_config(layout="wide")

# Fetch Data
live_count = get_live_ghl_count()
gc = get_client()

# Show the big number immediately to stop the loop
st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; margin:0;">{live_count}</p>', unsafe_allow_html=True)

# Secondary Data
if gc:
    try:
        sheet = gc.open(SHEET_NAME).sheet1
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        # Add any yesterday/today sheet counts here if needed
        st.write(f"Sheet Connected: {len(df)} records found.")
    except:
        st.write("Google Sheet connected but failed to read rows.")
else:
    st.error("Google Auth Failed - Check gcp_service_account in Render")

# Auto-refresh
time.sleep(60)
st.rerun()
