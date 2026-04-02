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

# --- 3. DATA FETCHING (INCLUDES DUPLICATES) ---
def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        data = sheet.get_all_values()
        if len(data) < 2: return [] # Handle empty sheet
        
        # Column A = ID, Column B = Timestamp, Column C = Name
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # Clean and convert timestamps
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        # Standardize to UTC for comparison
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        # Define range
        cutoff = end_time if end_time else datetime.now(timezone.utc) + timedelta(days=1)
        
        # Filter by time period
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < cutoff)
        filtered_df = df[mask].copy()

        # RETURN ALL ROWS (Deduplication Logic Removed)
        return filtered_df.to_dict('records')

    except Exception as e:
        st.error(f"Data Fetch Error: {e}")
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
        # Open the sheet and get data
        sheet = client.open(SHEET_NAME).sheet1
        
        now_utc = datetime.now(timezone.utc)
        # Determine current shift start (12:00 UTC)
        if now_utc.hour >= 12:
            curr_start = now_utc.replace(hour=12, minute=0, second=0, microsecond=0)
        else:
            curr_start = (now_utc - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        
        prev_start = curr_start - timedelta(days=1)
        prev_end = curr_start

        # Fetch Data
        current_sales = fetch_sales_data(sheet, curr_start)
        previous_sales = fetch_sales_data(sheet, prev_start, prev_end)
        
        display_count = len(current_sales)
        count_prev = len(previous_sales)

        # Trigger Sound if count increases
        if display_count > st.session_state.last_count and st.session_state.last_count > 0:
            trigger_sound("cha-ching.mp3")
        st.session_state.last_count = display_count

        # --- RENDERING ---
        st.markdown('<p style="font-size:40px; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom:-20px;">LIVE SALES TODAY</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; line-height:0.8; margin:0;">{display_count}</p>', unsafe_allow_html=True)
        
        # Progress Bar
        progress_val = min(float(display_count) / float(DAILY_GOAL), 1.0)
        st.progress(progress_val)
        st.markdown(f"<center><b style='color:#39FF14; font-size:25px;'>Goal Progress: {display_count}/{DAILY_GOAL}</b></center>", unsafe_allow_html=True)
        
        # Yesterday Stats
        st.markdown(f'<p style="font-size:45px; color:#888888; text-align:center; font-weight:bold; margin-bottom:0;">Yesterday: {count_prev}</p>', unsafe_allow_html=True)
        
        # Timestamp in EST
        now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
        st.markdown(f'<p style="font-size:16px; text-align:center; color:#666666; margin-top:0;">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

        st.divider()
        
        # Detailed Lists
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<h3 style='color: white;'>New Sales:</h3>", unsafe_allow_html=True)
            for s in current_sales: 
                # Note: 'name' must match your column header exactly in Google Sheets
                name_val = s.get('name', 'Unknown')
                st.markdown(f"<span style='color: white;'>✔ {name_val}</span>", unsafe_allow_html=True)
        with c2:
            st.markdown("<h3 style='color: #888888;'>Yesterday's Sales:</h3>", unsafe_allow_html=True)
            for s in previous_sales: 
                name_val = s.get('name', 'Unknown')
                st.markdown(f"<span style='color: #888888;'>• {name_val}</span>", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Display Error: {e}")
else:
    st.error("Google Auth Failed. Check your GCP Service Account environment variable.")

# Refresh logic
time.sleep(60)
st.rerun()
