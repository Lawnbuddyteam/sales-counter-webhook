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
    # Look for GHL key (Case-Insensitive Search)
    ghl_key = None
    for k, v in os.environ.items():
        if k.lower() == "ghl_api_key":
            ghl_key = v
            break
            
    if not ghl_key:
        return 0, "Missing GHL_API_KEY"
    
    # Clean the token of any accidental braces/quotes from Render
    clean_key = ghl_key.replace('{', '').replace('}', '').replace('"', '').replace("'", "").strip()
    
    now_utc = datetime.now(timezone.utc)
    # Today starts at 9 AM ET (13:00 UTC)
    if now_utc.hour >= 13:
        start_time = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
    else:
        start_time = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)

    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {
        "Authorization": f"Bearer {clean_key}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }
    payload = {
        "locationId": LOCATION_ID,
        "pageLimit": 100,
        "filters": [{"field": "updatedAt", "operator": "gte", "value": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code != 200: return 0, f"GHL Err {r.status_code}"
        contacts = r.json().get('contacts', [])
        
        # Count only if 'client' tag is present and timestamp is valid
        count = 0
        for c in contacts:
            tags = [t.lower() for t in c.get('tags', [])]
            if "client" in tags:
                upd = c.get('updatedAt', '').replace('Z', '+00:00')
                if upd and datetime.fromisoformat(upd) >= start_time:
                    count += 1
        return count, "OK"
    except: return 0, "GHL Timeout"

# --- 3. GOOGLE AUTH (CASE-INSENSITIVE) ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Force search for the key regardless of case
    creds_json = None
    for k, v in os.environ.items():
        if k.lower() == "gcp_service_account":
            creds_json = v
            break

    if not creds_json:
        return None, "Key 'gcp_service_account' not found."

    try:
        creds_info = json.loads(creds_json)
        if 'private_key' in creds_info:
            creds_info['private_key'] = creds_info['private_key'].replace('\\n', '\n')
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        return gspread.authorize(creds), "OK"
    except Exception as e:
        return None, f"JSON Error: {str(e)[:50]}"

# --- 4. DATA PROCESSING ---
def fetch_sales_data(sheet, start_time):
    try:
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        mask = (df['timestamp'] >= start_time)
        return df[mask].drop_duplicates(subset=['name']).to_dict('records')
    except: return []

# --- 5. MAIN UI ---
st.set_page_config(layout="wide")

client, auth_status = get_gspread_client()

if client:
    try:
        sheet = client.open(SHEET_NAME).sheet1
        
        # Calculate Current Window Start
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour >= 13:
            curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
        else:
            curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
        
        count_curr, ghl_status = get_live_ghl_count()
        sheet_sales = fetch_sales_data(sheet, curr_start)

        # BIG DISPLAY
        st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; margin:0;">{count_curr}</p>', unsafe_allow_html=True)
        st.progress(min(count_curr/DAILY_GOAL, 1.0))
        
        c1, c2 = st.columns(2)
        c1.metric("Today (Sheet Count)", len(sheet_sales))
        
        if ghl_status != "OK": 
            st.warning(f"GHL Connection: {ghl_status}")
            
    except Exception as e:
        st.error(f"Sheet Access Error: {e}")
else:
    st.error(f"Google Auth: {auth_status}")

# Auto-refresh every 60 seconds
time.sleep(60)
st.rerun()
