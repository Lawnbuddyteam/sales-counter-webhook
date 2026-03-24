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

# --- 2. GHL V2 LIVE FETCH (REFINED TIME WINDOW) ---
def get_live_ghl_count():
    if not GHL_API_KEY:
        st.error("GHL_API_KEY not found in Render Environment Variables")
        return 0
    
    # Calculate Today's Start (1 PM UTC / 9 AM EDT)
    now_utc = datetime.now(timezone.utc)
    
    # Rollover Logic: If current time is after 13:00 UTC, Today started at 13:00 UTC today.
    # If before 13:00 UTC, Today started at 13:00 UTC yesterday.
    if now_utc.hour >= 13:
        start_time = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
    else:
        start_time = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)

    # We fetch EVERYTHING from the last 24 hours to ensure no 'edge cases' are missed by GHL's API
    fetch_buffer = start_time - timedelta(hours=2) 
    
    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {
        "Authorization": f"Bearer {GHL_API_KEY}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }
    
    payload = {
        "locationId": LOCATION_ID,
        "pageLimit": 100,
        "filters": [
            {
                "field": "updatedAt", 
                "operator": "gte", 
                "value": fetch_buffer.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            }
        ]
    }
    
    all_batch_contacts = []
    try:
        while True:
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            if r.status_code != 200: break
            
            data = r.json()
            batch = data.get('contacts', [])
            all_batch_contacts.extend(batch)
            
            next_page = data.get('meta', {}).get('nextPageId')
            if not next_page or not batch: break
            payload["searchAfter"] = next_page

        # --- PRECISE PYTHON FILTERING ---
        valid_count = 0
        for c in all_batch_contacts:
            # 1. Check for 'client' tag (Case-insensitive)
            tags = [t.lower().strip() for t in c.get('tags', [])]
            if "client" in tags:
                # 2. Precise Time Comparison
                upd_str = c.get('updatedAt', '').replace('Z', '+00:00')
                if upd_str:
                    upd_dt = datetime.fromisoformat(upd_str)
                    # If updated strictly AFTER 9 AM ET today, count it
                    if upd_dt >= start_time:
                        valid_count += 1
        return valid_count
    except:
        return 0

# --- 3. AUTH & AUDIO ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_info = json.loads(st.secrets["gcp_service_account"].strip())
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    else:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        except: return None
    return gspread.authorize(creds)

@st.cache_data
def get_audio_base64(file_path):
    try:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    except: return None

def trigger_sound(file_path):
    b64 = get_audio_base64(file_path)
    if b64:
        st.markdown(f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', unsafe_allow_html=True)

# --- 4. DATA FETCHING (GOOGLE SHEETS) ---
def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0]).tail(500)
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

# --- 5. SESSION STATE & SETUP ---
st.set_page_config(page_title="Sales Dashboard", layout="wide")

if 'last_count' not in st.session_state: st.session_state.last_count = 0
if 'celebrated' not in st.session_state: st.session_state.celebrated = False

placeholder = st.empty()
client = get_gspread_client()
sheet = client.open(SHEET_NAME).sheet1

# Day Bounds (1 PM UTC / 9 AM ET)
now_utc = datetime.now(timezone.utc)
if now_utc.hour >= 13:
    curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
else:
    curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
prev_start, prev_end = curr_start - timedelta(days=1), curr_start

# Fetch Counts
count_curr = get_live_ghl_count()
current_sales = fetch_sales_data(sheet, curr_start)
previous_sales = fetch_sales_data(sheet, prev_start, prev_end)
count_prev = len(previous_sales)

# --- 6. SOUND & CELEBRATION LOGIC ---
if count_curr > st.session_state.last_count:
    if count_curr >= DAILY_GOAL and not st.session_state.celebrated:
        st.balloons()
        trigger_sound("champions.mp3")
        st.session_state.celebrated = True
    elif st.session_state.last_count > 0: # Only cha-ching if it's a new sale after start
        trigger_sound("cha-ching.mp3")
st.session_state.last_count = count_curr

# --- 7. UI RENDERING ---
with placeholder.container():
    st.markdown(f'<p style="font-size:40px; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom:-20px;">LIVE SALES TODAY</p>', unsafe_allow_html=True)
    
    text_color = "#39FF14" if count_curr >= DAILY_GOAL else "#FFFFFF"
    glow = "text-shadow: 0 0 20px #39FF14;" if count_curr >= DAILY_GOAL else ""
    st.markdown(f'<p style="font-size:320px; text-align:center; color:{text_color}; font-weight:900; line-height:0.8; margin:0; {glow}">{count_curr}</p>', unsafe_allow_html=True)
    
    progress_val = min(float(count_curr) / float(DAILY_GOAL), 1.0)
    st.progress(progress_val)
    st.markdown(f"<center><b style='color:#39FF14; font-size:25px;'>Goal Progress: {count_curr}/{DAILY_GOAL}</b></center>", unsafe_allow_html=True)
    
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

# --- 8. AUTO-REFRESH ---
time.sleep(60)
st.rerun()
