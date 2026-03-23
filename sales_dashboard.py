import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import time
import json
import base64

# --- 1. CONFIGURATION ---
DAILY_GOAL = 70
SHEET_NAME = "Sales_Counter" 

# --- 2. AUTHENTICATION & AUDIO CACHING ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_info = json.loads(st.secrets["gcp_service_account"].strip())
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
    return gspread.authorize(creds)

@st.cache_data
def get_audio_base64(file_path):
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return None

def trigger_sound(file_path):
    b64 = get_audio_base64(file_path)
    if b64:
        st.markdown(
            f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>',
            unsafe_allow_html=True
        )

# --- 3. DATA FETCHING ---
def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        data = sheet.get_all_values()
        # Use tail to keep processing fast and avoid 408 timeouts
        df = pd.DataFrame(data[1:], columns=data[0]).tail(200)
        if df.empty: return []
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time) if end_time else (df['timestamp'] >= start_time)
        filtered_df = df[mask].copy()
        
        # Deduplication logic for the display
        filtered_df['name_clean'] = filtered_df['name'].astype(str).fillna('').str.strip().str.lower()
        return filtered_df.drop_duplicates(subset=['name_clean'], keep='first').to_dict('records')
    except:
        return []

# --- 4. MAIN LOGIC & STATE ---
if 'last_count' not in st.session_state:
    st.session_state.last_count = 0
if 'celebrated' not in st.session_state:
    st.session_state.celebrated = False

# Connect to Sheet
client = get_gspread_client()
sheet = client.open(SHEET_NAME).sheet1

# Calculate Bounds (1 PM UTC is 9 AM EST)
now_utc = datetime.now(timezone.utc)
curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
if now_utc.hour < 13: 
    curr_start -= timedelta(days=1)
prev_start, prev_end = curr_start - timedelta(days=1), curr_start

# Fetch Sales
current_sales = fetch_sales_data(sheet, curr_start)
previous_sales = fetch_sales_data(sheet, prev_start, prev_end)
count_curr = len(current_sales)
count_prev = len(previous_sales)

# --- 5. SOUND TRIGGER ---
# This must run before UI rendering to avoid delay
if count_curr > st.session_state.last_count:
    if count_curr >= DAILY_GOAL and not st.session_state.celebrated:
        st.balloons()
        trigger_sound("champions.mp3")
        st.session_state.celebrated = True
    elif count_curr < DAILY_GOAL:
        trigger_sound("cha-ching.mp3")

st.session_state.last_count = count_curr
if count_curr < DAILY_GOAL: 
    st.session_state.celebrated = False

# --- 6. UI RENDERING ---
# Wrapping in a container prevents the "grayscale" ghosting effect
with st.container():
    # Header
    st.markdown(f'<p style="font-size:40px; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom:-20px;">LIVE SALES TODAY</p>', unsafe_allow_html=True)
    
    # Big Number
    text_color = "#39FF14" if count_curr >= DAILY_GOAL else "#FFFFFF"
    glow = "text-shadow: 0 0 20px #39FF14;" if count_curr >= DAILY_GOAL else ""
    st.markdown(f'<p style="font-size:320px; text-align:center; color:{text_color}; font-weight:900; line-height:0.8; margin:0; {glow}">{count_curr}</p>', unsafe_allow_html=True)
    
    # Progress Bar
    progress_val = min(float(count_curr) / float(DAILY_GOAL), 1.0)
    st.progress(progress_val)
    st.markdown(f"<center><b style='color:#39FF14; font-size:25px;'>Goal Progress: {count_curr} / {DAILY_GOAL}</b></center>", unsafe_allow_html=True)

    # Secondary Stats
    st.markdown(f'<p style="font-size:45px; color:#888888; text-align:center; font-weight:bold;">Yesterday: {count_prev}</p>', unsafe_allow_html=True)
    
    now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
    st.markdown(f'<p style="font-size:14px; text-align:center; color:#444444;">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

    # Audit Logs
    st.divider()
    test_mode = st.checkbox("Show Audit Lists", value=True)
    if test_mode:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("<h3 style='color: #5D9CEC;'>Today (A-Z)</h3>", unsafe_allow_html=True)
            for c in sorted(current_sales, key=lambda x: x['name']):
                st.write(f"✔ {c['name']}")
        with col2:
            st.markdown("<h3 style='color: #888888;'>Yesterday</h3>", unsafe_allow_html=True)
            for c in sorted(previous_sales, key=lambda x: x['name']):
                st.write(f"• {c['name']}")

# --- 7. REFRESH LOOP ---
time.sleep(60)
st.rerun()
