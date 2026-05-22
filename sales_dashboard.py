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
DAILY_GOAL = 90
SHEET_NAME = "Sales_Counter" 
LOCATION_ID = "snQISHLOuYGlR3jXbGU3"
GHL_API_KEY = os.environ.get('GHL_API_KEY')

# --- 2. AUTH & AUDIO ---
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
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    except: return None

def trigger_sound(file_path):
    b64 = get_audio_base64(file_path)
    if b64:
        st.markdown(f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', unsafe_allow_html=True)

# --- 3. DATA FETCHING (WITH RETRIES & FALLBACKS) ---

def get_worksheet_with_retries(client, sheet_name):
    """Attempts to open the worksheet with retries for transient API 500 errors."""
    for attempt in range(3):
        try:
            return client.open(sheet_name).sheet1
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise e

@st.cache_data(ttl=120, show_spinner=False)
def fetch_all_sheet_data(_sheet):
    """Fetches sheet data with a 3-attempt retry loop. Fails loud so Streamlit doesn't cache a failure."""
    for attempt in range(3):
        try:
            return _sheet.get_all_values()
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise e

def process_sales_data(data, start_time, end_time=None):
    try:
        if len(data) < 2: return [] 
        
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

# --- 4. MAIN UI ---
st.set_page_config(layout="wide", page_title="Sales Dashboard")

st.markdown("""
    <style>
        .stProgress > div > div > div > div {
            background-color: #39FF14;
            box-shadow: 0 0 10px #39FF14;
        }
        body {
            background-color: #0E1117;
        }
    </style>
    """, unsafe_allow_html=True)

if 'last_count' not in st.session_state: st.session_state.last_count = 0

client = get_gspread_client()
if client:
    try:
        # Step A: Get sheet with retries
        sheet = get_worksheet_with_retries(client, SHEET_NAME)
        
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour >= 4:
            curr_start = now_utc.replace(hour=4, minute=0, second=0, microsecond=0)
        else:
            curr_start = (now_utc - timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
        
        prev_start = curr_start - timedelta(days=1)
        prev_end = curr_start

        # Step B: Fetch data with retries, and store it in session state
        try:
            fresh_data = fetch_all_sheet_data(sheet)
            st.session_state.cached_sheet_data = fresh_data
        except Exception:
            # If Google completely fails, we silently pass and use the previous cycle's data
            pass
        
        # Step C: Fallback check. If first-time load fails, wait and restart.
        if 'cached_sheet_data' not in st.session_state:
            st.warning("Google API is temporarily unavailable. Retrying connection...")
            time.sleep(5)
            st.rerun()

        # Safely proceed with data
        all_data = st.session_state.cached_sheet_data

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
        st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; line-height:0.8; margin:0;">{display_count}</p>', unsafe_allow_html=True)
        
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
else:
    st.error("Google Auth Failed.")

# --- 5. DYNAMIC REFRESH SCHEDULING ---
current_hour = (datetime.now(timezone.utc) - timedelta(hours=4)).hour

if 4 <= current_hour < 18:
    sleep_seconds = 120
else:
    sleep_seconds = 600

time.sleep(sleep_seconds)
st.rerun()
