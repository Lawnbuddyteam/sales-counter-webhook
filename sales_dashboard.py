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

# LOOK FOR KEY IN TWO PLACES
GHL_API_KEY = os.environ.get('GHL_API_KEY') or st.secrets.get('GHL_API_KEY')

def get_live_ghl_count():
    if not GHL_API_KEY:
        return 0, "Missing API Key in Render"
    
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour >= 13:
        start_time = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
    else:
        start_time = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)

    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {
        "Authorization": f"Bearer {GHL_API_KEY.strip()}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }
    
    payload = {
        "locationId": LOCATION_ID,
        "pageLimit": 100,
        "filters": [{"field": "updatedAt", "operator": "gte", "value": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        if r.status_code == 401: return 0, "Invalid/Expired Token"
        if r.status_code != 200: return 0, f"Error {r.status_code}"
            
        contacts = r.json().get('contacts', [])
        valid_count = 0
        for c in contacts:
            tags = [t.lower().strip() for t in c.get('tags', [])]
            if "client" in tags:
                upd_str = c.get('updatedAt', '').replace('Z', '+00:00')
                if upd_str and datetime.fromisoformat(upd_str) >= start_time:
                    valid_count += 1
        return valid_count, "OK"
    except:
        return 0, "Connection Error"

# --- 2. AUTH & DATA (FORCED REFRESH) ---
def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        # We don't use st.cache here so it pulls fresh every 60 seconds
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time) if end_time else (df['timestamp'] >= start_time)
        return df[mask].drop_duplicates(subset=['name']).to_dict('records')
    except: return []

# --- 3. MAIN UI ---
st.set_page_config(layout="wide")

# Google Auth
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get('GCP_SERVICE_ACCOUNT') or st.secrets.get('gcp_service_account')
    creds_info = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    return gspread.authorize(creds)

try:
    gc = get_client()
    sheet = gc.open(SHEET_NAME).sheet1
except Exception as e:
    st.error(f"Google Connection Failed: {e}")
    st.stop()

# Time Windows
now_utc = datetime.now(timezone.utc)
if now_utc.hour >= 13:
    curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
else:
    curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
prev_start, prev_end = curr_start - timedelta(days=1), curr_start

# FETCH ALL
count_curr, status = get_live_ghl_count()
current_sales = fetch_sales_data(sheet, curr_start)
previous_sales = fetch_sales_data(sheet, prev_start, prev_end)

# DISPLAY
st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; margin:0;">{count_curr}</p>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
c1.metric("Today (Sheet)", len(current_sales))
c2.metric("Yesterday (Sheet)", len(previous_sales))

if status != "OK":
    st.warning(f"GHL Debug: {status}")

time.sleep(60)
st.rerun()
