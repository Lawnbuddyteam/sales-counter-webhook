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

# Render environment variables
GHL_API_KEY = os.environ.get('GHL_API_KEY')

def get_live_ghl_count():
    if not GHL_API_KEY:
        return 0
    
    # Calculate Today's Start (1 PM UTC / 9 AM EST)
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=13, minute=0, second=0, microsecond=0)
    if now.hour < 13: 
        start_time -= timedelta(days=1)
    
    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {
        "Authorization": f"Bearer {GHL_API_KEY.strip()}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }
    # FIXED: Using 'updatedAt' which is the correct indexed field for GHL V2 Search
    payload = {
        "locationId": LOCATION_ID,
        "filters": [{"field": "updatedAt", "operator": "gte", "value": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            contacts = r.json().get('contacts', [])
            clients = [c for c in contacts if "client" in [t.lower() for t in c.get('tags', [])]]
            return len(clients)
    except:
        return 0
    return 0

# --- 2. AUTH & AUDIO ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Try Render Environment Variable first, then Fallback to st.secrets
    creds_json = os.environ.get('gcp_service_account') or os.environ.get('GCP_SERVICE_ACCOUNT')
    
    if creds_json:
        creds_info = json.loads(creds_json)
    elif "gcp_service_account" in st.secrets:
        creds_info = json.loads(st.secrets["gcp_service_account"].strip())
    else:
        # Last resort fallback to local file
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
            return gspread.authorize(creds)
        except:
            return None

    # Fix the private key newline issue common in environment variables
    if 'private_key' in creds_info:
        creds_info['private_key'] = creds_info['private_key'].replace('\\n', '\n')
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    return gspread.authorize(creds)

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

# --- 3. DATA FETCHING ---
def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        # We fetch fresh values without caching to ensure the Sheet updates
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0]).tail(300)
        if df.empty: return []
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time) if end_time else (df['timestamp'] >= start_time)
        filtered_df = df[mask].copy()
        
        filtered_df['name_clean'] = filtered_df['name'].astype(str).str.strip()
        unique_df = filtered_df.drop_duplicates(subset=['name_clean'], keep='first').copy()
        
        def get_last_name(fullname):
            parts = str(fullname).split()
            return parts[-1].lower() if len(parts) > 1 else str(fullname).lower()
        
        unique_df['ln_key'] = unique_df['name_clean'].apply(get_last_name)
        return unique_df.sort_values('ln_key').to_dict('records')
    except: return []

# --- 4. SESSION STATE & SETUP ---
st.set_page_config(layout="wide")

if 'last_count' not in st.session_state: st.session_state.last_count = 0
if 'celebrated' not in st.session_state: st.session_state.celebrated = False

placeholder = st.empty()
client = get_gspread_client()

if client:
    sheet = client.open(SHEET_NAME).sheet1

    # Day Bounds (1 PM UTC)
    now_utc = datetime.now(timezone.utc)
    curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
    if now_utc.hour < 13: curr_start -= timedelta(days=1)
    prev_start, prev_end = curr_start - timedelta(days=1), curr_start

    # Fetch Data
    ghl_live_count = get_live_ghl_count() # Fetch the actual GHL number
    current_sales = fetch_sales_data(sheet, curr_start)
    previous_sales = fetch_sales_data(sheet, prev_start, prev_end)
    count_prev = len(previous_sales)

    # --- 5. SOUND LOGIC ---
    # Trigger based on the GHL Live Count
    if ghl_live_count > st.session_state.last_count:
        if ghl_live_count >= DAILY_GOAL and not st.session_state.celebrated:
            st.balloons()
            trigger_sound("champions.mp3")
            st.session_state.celebrated = True
        elif st.session_state.last_count > 0: # Avoid playing on initial load
            trigger_sound("cha-ching.mp3")
    st.session_state.last_count = ghl_live_count

    # --- 6. UI RENDERING ---
    with placeholder.container():
        st.markdown(f'<p style="font-size:40px; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom:-20px;">LIVE SALES TODAY</p>', unsafe_allow_html=True)
        
        text_color = "#39FF14" if ghl_live_count >= DAILY_GOAL else "#FFFFFF"
        glow = "text-shadow: 0 0 20px #39FF14;" if ghl_live_count >= DAILY_GOAL else ""
        st.markdown(f'<p style="font-size:320px; text-align:center; color:{text_color}; font-weight:900; line-height:0.8; margin:0; {glow}">{ghl_live_count}</p>', unsafe_allow_html=True)
        
        progress_val = min(float(ghl_live_count) / float(DAILY_GOAL), 1.0)
        st.progress(progress_val)
        st.markdown(f"<center><b style='color:#39FF14; font-size:25px;'>Goal Progress: {ghl_live_count}/{DAILY_GOAL}</b></center>", unsafe_allow_html=True)
        
        now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
        st.markdown(f'<p style="font-size:16px; text-align:center; color:#666666; margin-top:5px;">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

        st.markdown(f'<p style="font-size:45px; color:#888888; text-align:center; font-weight:bold;">Yesterday: {count_prev}</p>', unsafe_allow_html=True)

        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("<h3 style='color: #5D9CEC;'>Sheet Logs:</h3>", unsafe_allow_html=True)
            for c in current_sales:
                st.write(f"✔ {c['name']}")
        with col2:
            st.markdown("<h3 style='color: #888888;'>Yesterday's Sales:</h3>", unsafe_allow_html=True)
            for c in previous_sales:
                st.write(f"• {c['name']}")
else:
    st.error("Waiting for Google Authentication... Please check Render environment variables.")

# --- 7. AUTO-REFRESH ---
time.sleep(60)
st.rerun()
