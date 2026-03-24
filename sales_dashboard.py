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
GHL_API_KEY = os.environ.get('GHL_API_KEY')
LOCATION_ID = "snQISHLOuYGlR3jXbGU3"

# --- 2. GHL V2 FETCH (WITH ERROR LOGGING) ---
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
        "Authorization": f"Bearer {GHL_API_KEY}",
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
        if r.status_code != 200:
            return 0, f"API Error {r.status_code}: {r.text[:50]}"
            
        contacts = r.json().get('contacts', [])
        valid_count = 0
        for c in contacts:
            tags = [t.lower().strip() for t in c.get('tags', [])]
            if "client" in tags:
                upd_str = c.get('updatedAt', '').replace('Z', '+00:00')
                if upd_str and datetime.fromisoformat(upd_str) >= start_time:
                    valid_count += 1
        return valid_count, "OK"
    except Exception as e:
        return 0, f"Conn Error: {str(e)[:30]}"

# --- 3. AUTH & DATA ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_info = json.loads(st.secrets["gcp_service_account"].strip())
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        return gspread.authorize(creds)
    except: return None

def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        # Clear cache to force fresh read from Google Sheets
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        # Localize to UTC for comparison
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time) if end_time else (df['timestamp'] >= start_time)
        filtered = df[mask].drop_duplicates(subset=['name'])
        return filtered.to_dict('records')
    except: return []

# --- 4. MAIN LOGIC ---
st.set_page_config(layout="wide")
client = get_gspread_client()
if not client:
    st.error("Google Auth Failed")
    st.stop()

sheet = client.open(SHEET_NAME).sheet1

# Time Calculations
now_utc = datetime.now(timezone.utc)
if now_utc.hour >= 13:
    curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
else:
    curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
prev_start, prev_end = curr_start - timedelta(days=1), curr_start

# GET COUNTS
count_curr, status = get_live_ghl_count()
current_sales = fetch_sales_data(sheet, curr_start)
previous_sales = fetch_sales_data(sheet, prev_start, prev_end)
count_prev = len(previous_sales)

# UI
st.markdown(f'<p style="font-size:320px; text-align:center; color:white; font-weight:900; line-height:0.8; margin:0;">{count_curr}</p>', unsafe_allow_html=True)
st.progress(min(count_curr/DAILY_GOAL, 1.0))

col1, col2 = st.columns(2)
col1.metric("Today (Sheet)", len(current_sales))
col2.metric("Yesterday (Sheet)", count_prev)

# DEBUG INFO (Small at bottom)
if status != "OK":
    st.warning(f"GHL Status: {status}")

# AUTO-REFRESH
time.sleep(60)
st.rerun()
