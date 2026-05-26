import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import time
import json
import os
import base64

# --- 0. PAGE CONFIG MUST BE FIRST ---
st.set_page_config(layout="wide", page_title="Sales Dashboard")

# --- 1. CONFIGURATION ---
DAILY_GOAL = 90
SHEET_NAME = "Sales_Counter" 
LOCATION_ID = "snQISHLOuYGlR3jXbGU3"
GHL_API_KEY = os.environ.get('GHL_API_KEY')

# --- 2. AUTH & AUDIO ---
@st.cache_resource(ttl=1800)
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
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    except: return None

def trigger_sound(file_path):
    b64 = get_audio_base64(file_path)
    if b64:
        st.markdown(f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', unsafe_allow_html=True)

# --- 3. DATA FETCHING ---
def get_fresh_data(sheet):
    """Fetches sheet data with a 3-attempt retry loop."""
    for attempt in range(3):
        try:
            return sheet.get_all_values()
        except Exception as e:
            if attempt < 2: time.sleep(2)
            else: raise e

def process_sales_data(data, start_time, end_time=None):
    try:
        if not data or len(data) < 2: return [] 
        
        df = pd.DataFrame(data[1:], columns=data[0])
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        dedup_threshold = datetime(2026, 4, 1, tzinfo=timezone.utc)
        
        legacy_df = df[df['timestamp'] < dedup_threshold].copy()
        current_df = df[df['timestamp'] >= dedup_threshold].copy()
        
        current_df = current_df.drop_duplicates(subset=[df.columns[0]], keep='first')
        final_df = pd.concat([legacy_df, current_df])
        
        cutoff = end_time if end_time else datetime.now(timezone.utc) + timedelta(days=1)
        mask = (final_df['timestamp'] >= start_time) & (final_df['timestamp'] < cutoff)
        filtered_df = final_df[mask].copy()

        if not filtered_df.empty:
            filtered_df['sort_name'] = filtered_df.iloc[:, 2].astype(str).apply(lambda x: x.split()[-1] if x.split() else "")
            filtered_df = filtered_df.sort_values(by='sort_name', ascending=True)

        return filtered_df.to_dict('records')
    except Exception as e:
        st.error(f"Data Processing Error: {e}")
        return []

# --- 4. STARTUP UI (Unlocks Audio on iPad) ---
if 'dashboard_started' not in st.session_state:
    st.session_state.dashboard_started = False

if not st.session_state.dashboard_started:
    st.markdown("<h1 style='text-align: center; margin-top: 20vh; color: white;'>Sales Dashboard Ready</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #888;'>Tap the button below on the iPad to unlock audio autoplay permissions.</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Start Dashboard", use_container_width=True):
            st.session_state.dashboard_started = True
            st.rerun()
    st.stop() # Halts execution until the user taps the button

# --- 5. NATIVE AUTO-REFRESH & MAIN UI ---
st.markdown("""
    <style>
        .stProgress > div > div > div > div {
            background-color: #39FF14;
            box-shadow: 0 0 10px #39FF14;
        }
    </style>
    """, unsafe_allow_html=True)

# Determine the refresh rate based on the time of day
current_hour = (datetime.now(timezone.utc) - timedelta(hours=4)).hour
refresh_seconds = 120 if 4 <= current_hour < 18 else 600 

# Streamlit's native fragment handles the loop safely without breaking iOS WebSockets
@st.fragment(run_every=refresh_seconds)
def render_live_dashboard():
    if 'last_count' not in st.session_state: st.session_state.last_count = 0

    client = get_gspread_client()
    if not client:
        st.error("Google Auth Failed. Please check service account credentials.")
        return

    try:
        sheet = client.open(SHEET_NAME).sheet1
        
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour >= 4:
            curr_start = now_utc.replace(hour=4, minute=0, second=0, microsecond=0)
        else:
            curr_start = (now_utc - timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
        
        prev_start = curr_start - timedelta(days=1)
        prev_end = curr_start

        # Fetch fresh data (The fragment timer replaces our old manual cache logic)
        try:
            all_data = get_fresh_data(sheet)
        except Exception as e:
            st.warning("Brief connection drop to Google. Retrying next cycle...")
            return

        current_sales = process_sales_data(all_data, curr_start)
        previous_sales = process_sales_data(all_data, prev_start, prev_end)
        
        display_count = len(current_sales)
        count_prev = len(previous_sales)

        # CELEBRATION LOGIC
        if display_count > st.session_state.last_count and st.session_state.last_count > 0:
            if display_count >= DAILY_GOAL:
                st.balloons()
                trigger_sound("champions.mp3")
            else:
                trigger_sound("cha-ching.mp3")
                
        st.session_state.last_count = display_count

        # RENDERING
        st.markdown('<p style="font-size:40px; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom:-20px;">CONVERSIONS TODAY</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:20vw; text-align:center; color:white; font-weight:900; line-height:0.8; margin:0;">{display_count}</p>', unsafe_allow_html=True)
        
        progress_val = min(float(display_count) / float(DAILY_GOAL), 1.0)
        st.progress(progress_val)
        st.markdown(f"<center><b style='color:#39FF14; font-size:25px;'>Goal Progress: {display_count}/{DAILY_GOAL}</b></center>", unsafe_allow_html=True)
        
        st.markdown(f'<p style="font-size:45px; color:#888888; text-align:center; font-weight:bold; margin-bottom:0;">Yesterday: {count_prev}</p>', unsafe_allow_html=True)
        
        now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
        st.markdown(f'<p style="font-size:16px; text-align:center; color:#666666; margin-top:0;">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

        st.divider()
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<h3 style='color: white;'>New Sales:</h3>", unsafe_allow_html=True)
            for s in current_sales: 
                name_val = s.get(list(s.keys())[2], 'Unknown')
                st.markdown(f"<span style='color: white;'>✔ {name_val}</span>", unsafe_allow_html=True)
        with c2:
            st.markdown("<h3 style='color: #888888;'>Yesterday's Sales:</h3>", unsafe_allow_html=True)
            for s in previous_sales: 
                name_val = s.get(list(s.keys())[2], 'Unknown')
                st.markdown(f"<span style='color: #888888;'>• {name_val}</span>", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Display Error: {e}")

# Call the fragment function to start the loop
render_live_dashboard()
