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

# --- 2. AUTH & AUDIO ---
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
    except: return None

def trigger_sound(file_path):
    b64 = get_audio_base64(file_path)
    if b64:
        st.markdown(f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', unsafe_allow_html=True)

# --- 3. DATA FETCHING (FIXED SORTING) ---
def fetch_sales_data(sheet, start_time):
    try:
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0]).tail(200)
        if df.empty: return []
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC') if df['timestamp'].dt.tz is None else df['timestamp'].dt.tz_convert('UTC')
        
        filtered_df = df[df['timestamp'] >= start_time].copy()
        filtered_df['name_clean'] = filtered_df['name'].astype(str).str.strip()
        unique_df = filtered_df.drop_duplicates(subset=['name_clean'], keep='first').copy()
        
        # --- FIX 1: SORT BY LAST NAME ---
        def get_last_name(fullname):
            parts = str(fullname).split()
            return parts[-1].lower() if len(parts) > 1 else str(fullname).lower()
        
        unique_df['last_name_key'] = unique_df['name_clean'].apply(get_last_name)
        return unique_df.sort_values('last_name_key').to_dict('records')
    except: return []

# --- 4. SESSION STATE ---
if 'last_count' not in st.session_state: st.session_state.last_count = 0
if 'celebrated' not in st.session_state: st.session_state.celebrated = False

# --- 5. MAIN LOOP ---
# Create a placeholder to prevent the "grayscale" ghosting reprint
placeholder = st.empty()

client = get_gspread_client()
sheet = client.open(SHEET_NAME).sheet1

# Calculate Today's Bounds (1 PM UTC)
now_utc = datetime.now(timezone.utc)
curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
if now_utc.hour < 13: curr_start -= timedelta(days=1)

current_sales = fetch_sales_data(sheet, curr_start)
count_curr = len(current_sales)

# --- FIX 2: SOUND TRIGGER ---
if count_curr > st.session_state.last_count:
    if count_curr >= DAILY_GOAL and not st.session_state.celebrated:
        st.balloons()
        trigger_sound("champions.mp3")
        st.session_state.celebrated = True
    else:
        trigger_sound("cha-ching.mp3")
st.session_state.last_count = count_curr

# --- FIX 3: UI RENDERING (NO GHOSTING) ---
with placeholder.container():
    # Big Number Display
    st.markdown(f'<p style="font-size:40px; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom:-20px;">LIVE SALES TODAY</p>', unsafe_allow_html=True)
    text_color = "#39FF14" if count_curr >= DAILY_GOAL else "#FFFFFF"
    st.markdown(f'<p style="font-size:320px; text-align:center; color:{text_color}; font-weight:900; line-height:0.8; margin:0;">{count_curr}</p>', unsafe_allow_html=True)
    
    # Progress Bar
    progress_val = min(float(count_curr) / float(DAILY_GOAL), 1.0)
    st.progress(progress_val)
    st.markdown(f"<center><b style='color:#39FF14; font-size:25px;'>Goal: {count_curr}/{DAILY_GOAL}</b></center>", unsafe_allow_html=True)

    # Audit Logs
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Today's Closers (Last Name A-Z)")
        for c in current_sales:
            st.write(f"✔ {c['name']}")
    with col2:
        st.write(" ") # Space for future stats
        now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M %p')
        st.metric("Last Sync", now_est)

# Automatic Refresh
time.sleep(60)
st.rerun()
