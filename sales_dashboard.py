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

# Pull GHL Key from Render
GHL_API_KEY = os.environ.get('GHL_API_KEY')

# --- 2. GOOGLE AUTH (FROM SINGLE JSON BLOCK) ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # Pull the big JSON string from Render
        creds_json = os.environ.get('GCP_SERVICE_ACCOUNT')
        if not creds_json:
            st.error("GCP_SERVICE_ACCOUNT variable not found in Render.")
            return None
            
        creds_info = json.loads(creds_json)
        
        # Ensure the private key handles newlines correctly
        if 'private_key' in creds_info:
            creds_info['private_key'] = creds_info['private_key'].replace('\\n', '\n')
            
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Auth Failed: {e}")
        return None

# --- 3. GHL FETCH ---
def get_live_ghl_count():
    if not GHL_API_KEY:
        return 0, "Missing GHL_API_KEY in Render"
    
    # Clean the key in case user left quotes/braces in Render
    clean_key = GHL_API_KEY.replace('{', '').replace('}', '').replace('"', '').replace("'", "").strip()
    
    now_utc = datetime.now(timezone.utc)
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
        if r.status_code == 401: return 0, "Invalid GHL Token"
        if r.status_code != 200: return 0, f"GHL Error {r.status_code}"
        
        contacts = r.json().get('contacts', [])
        count = 0
        for c in contacts:
            tags = [t.lower() for t in c.get('tags', [])]
            if "client" in tags:
                upd = c.get('updatedAt', '').replace('Z', '+00:00')
                if upd and datetime.fromisoformat(upd) >= start_time:
                    count += 1
        return count, "OK"
    except: return 0, "GHL Conn Timeout"

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
st.set_page_config(page_title="Sales Dashboard", layout="wide")

client = get_gspread_client()
if client:
    try:
        sheet = client.open(SHEET_NAME).sheet1
        
        # Time Windows
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour >= 13:
            curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
        else:
            curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
        prev_start, prev_end = curr_start - timedelta(days=1), curr_start

        # Counts
        count_curr, status = get_live_ghl_count()
        current_sales = fetch_sales_data(sheet, curr_start)
        previous_sales = fetch_sales_data(sheet, prev_start, prev_end)

        # Big Display
        st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; margin:0;">{count_curr}</p>', unsafe_allow_html=True)
        st.progress(min(count_curr/DAILY_GOAL, 1.0))

        c1, c2 = st.columns(2)
        c1.metric("Today (Sheet)", len(current_sales))
        c2.metric("Yesterday (Sheet)", len(previous_sales))
        
        if status != "OK": st.warning(f"Status: {status}")

    except Exception as e:
        st.error(f"Sheet Error: {e}")
else:
    st.error("Waiting for Google Authorization...")

time.sleep(60)
st.rerun()
