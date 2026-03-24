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
GHL_API_KEY = os.environ.get('GHL_API_KEY')

# --- 2. GHL LIVE FETCH (FIXED FILTER) ---
def get_live_ghl_count():
    if not GHL_API_KEY: return 0
    token = GHL_API_KEY.strip()
    
    now = datetime.now(timezone.utc)
    if now.hour >= 13:
        start_time = now.replace(hour=13, minute=0, second=0, microsecond=0)
    else:
        start_time = (now - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)

    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {"Authorization": f"Bearer {token}", "Version": "2021-04-15", "Content-Type": "application/json"}
    
    # FIXED: 'updatedAt' is the correct GHL V2 field for 'gte' filters
    payload = {
        "locationId": LOCATION_ID,
        "filters": [{"field": "updatedAt", "operator": "gte", "value": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        contacts = r.json().get('contacts', [])
        # Count only if tagged with 'client'
        return sum(1 for c in contacts if "client" in [t.lower() for t in c.get('tags', [])])
    except:
        return 0

# --- 3. AUTH & AUDIO ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get('gcp_service_account') or os.environ.get('GCP_SERVICE_ACCOUNT')
    if not creds_json: return None
    try:
        info = json.loads(creds_json)
        if 'private_key' in info:
            info['private_key'] = info['private_key'].replace('\\n', '\n')
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
        return gspread.authorize(creds)
    except: return None

@st.cache_data
def get_audio_base64(file_path):
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except: return None

def trigger_sound(file_path):
    b64 = get_audio_base64(file_path)
    if b64:
        st.markdown(f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', unsafe_allow_html=True)

# --- 4. DATA FETCHING ---
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
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time) if end_time else (df['timestamp'] >= start_time)
        return df[mask].drop_duplicates(subset=['name']).to_dict('records')
    except: return []

# --- 5. UI SETUP ---
st.set_page_config(layout="wide")
if 'last_count' not in st.session_state: st.session_state.last_count = 0

client = get_gspread_client()
if client:
    sheet = client.open(SHEET_NAME).sheet1
    
    # Calculate Times (9 AM ET / 13:00 UTC)
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour >= 13:
        curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
    else:
        curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
    prev_start, prev_end = curr_start - timedelta(days=1), curr_start

    # FETCH DATA
    live_count = get_live_ghl_count()
    current_sales = fetch_sales_data(sheet, curr_start)
    previous_sales = fetch_sales_data(sheet, prev_start, prev_end)
    count_prev = len(previous_sales)

    # --- 6. SOUND LOGIC ---
    if live_count > st.session_state.last_count and st.session_state.last_count > 0:
        trigger_sound("cha-ching.mp3")
    st.session_state.last_count = live_count

    # --- 7. UI RENDERING ---
    st.markdown('<p style="font-size:40px; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom:-20px;">LIVE SALES TODAY</p>', unsafe_allow_html=True)
    st.markdown(f'<p style="font-size:320px; text-align:center; color:white; font-weight:900; line-height:0.8; margin:0;">{live_count}</p>', unsafe_allow_html=True)
    
    st.progress(min(float(live_count) / DAILY_GOAL, 1.0))
    
    # Yesterday metric in Gray as requested
    st.markdown(f'<p style="font-size:45px; color:#888888; text-align:center; font-weight:bold;">Yesterday: {count_prev}</p>', unsafe_allow_html=True)

    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<h3 style='color: white;'>New Sales:</h3>", unsafe_allow_html=True)
        for s in current_sales: st.markdown(f"<span style='color: white;'>✔ {s['name']}</span>", unsafe_allow_html=True)
    with c2:
        st.markdown("<h3 style='color: #888888;'>Yesterday's Sales:</h3>", unsafe_allow_html=True)
        for s in previous_sales: st.markdown(f"<span style='color: #888888;'>• {s['name']}</span>", unsafe_allow_html=True)
else:
    st.error("Google Auth Failed.")

time.sleep(60)
st.rerun()
