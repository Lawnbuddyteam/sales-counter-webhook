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

# --- 2. GHL FETCH ---
def get_live_ghl_count():
    # Look for GHL key anywhere in environment
    ghl_key = os.environ.get('GHL_API_KEY')
    if not ghl_key:
        return 0, "Missing GHL_API_KEY"
    
    clean_key = ghl_key.replace('{', '').replace('}', '').replace('"', '').replace("'", "").strip()
    
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour >= 13:
        start_time = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
    else:
        start_time = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)

    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {"Authorization": f"Bearer {clean_key}", "Version": "2021-04-15", "Content-Type": "application/json"}
    payload = {
        "locationId": LOCATION_ID,
        "pageLimit": 100,
        "filters": [{"field": "updatedAt", "operator": "gte", "value": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code != 200: return 0, f"GHL Err {r.status_code}"
        contacts = r.json().get('contacts', [])
        count = sum(1 for c in contacts if "client" in [t.lower() for t in c.get('tags', [])])
        return count, "OK"
    except: return 0, "GHL Timeout"

# --- 3. GOOGLE AUTH (THE SEARCHER) ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Attempt to find the variable by direct name or similar name
    creds_json = os.environ.get('GCP_SERVICE_ACCOUNT')
    
    # If direct search fails, look through all keys for a match
    if not creds_json:
        for key in os.environ.keys():
            if 'GCP' in key and 'SERVICE' in key:
                creds_json = os.environ.get(key)
                break

    if not creds_json:
        return None, "Variable NOT found in environment."

    try:
        creds_info = json.loads(creds_json)
        if 'private_key' in creds_info:
            creds_info['private_key'] = creds_info['private_key'].replace('\\n', '\n')
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        return gspread.authorize(creds), "OK"
    except Exception as e:
        return None, f"JSON Parse Error: {str(e)[:50]}"

# --- 4. DATA PROCESSING ---
def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < (end_time if end_time else datetime.now(timezone.utc) + timedelta(days=1)))
        return df[mask].drop_duplicates(subset=['name']).to_dict('records')
    except: return []

# --- 5. MAIN UI ---
st.set_page_config(layout="wide")

client, auth_status = get_gspread_client()

if client:
    try:
        sheet = client.open(SHEET_NAME).sheet1
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour >= 13:
            curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
        else:
            curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
        
        count_curr, ghl_status = get_live_ghl_count()
        current_sales = fetch_sales_data(sheet, curr_start)

        st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; margin:0;">{count_curr}</p>', unsafe_allow_html=True)
        st.progress(min(count_curr/DAILY_GOAL, 1.0))
        
        c1, c2 = st.columns(2)
        c1.metric("Today (Sheet)", len(current_sales))
        if ghl_status != "OK": st.warning(f"GHL: {ghl_status}")

    except Exception as e:
        st.error(f"Sheet Access Error: {e}")
else:
    st.error(f"Google Auth Status: {auth_status}")
    # Temporary Debug: List available keys (values hidden)
    st.write("Available Env Keys:", list(os.environ.keys()))

time.sleep(60)
st.rerun()
