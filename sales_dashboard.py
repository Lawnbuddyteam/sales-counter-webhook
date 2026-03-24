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

# --- 3. DATA FETCHING & HYBRID DEDUPLICATION ---
def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        data = sheet.get_all_values()
        # Column A = ID, Column B = Timestamp, Column C = Name
        df = pd.DataFrame(data[1:], columns=data[0])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < (end_time if end_time else datetime.now(timezone.utc) + timedelta(days=1)))
        filtered_df = df[mask].copy()

        # --- HYBRID DEDUPE LOGIC ---
        # 1. Create a "Unique Key" 
        # If ID exists, use ID. If not, use Name + Date (to keep same-name people separate)
        def create_key(row):
            cid = str(row.get('id', '')).strip()
            if cid and cid.lower() != "no id" and cid != "":
                return cid
            # Fallback: Name + YYYY-MM-DD
            return f"{str(row['name']).strip()}_{row['timestamp'].strftime('%Y-%m-%d')}"

        filtered_df['uid'] = filtered_df.apply(create_key, axis=1)
        filtered_df = filtered_df.drop_duplicates(subset=['uid'])
        
        # Alphabetical Sort by Last Name
        def get_last_name(fullname):
            parts = str(fullname).strip().split()
            return parts[-1].lower() if len(parts) > 1 else str(fullname).lower()
        
        filtered_df['ln_key'] = filtered_df['name'].apply(get_last_name)
        return filtered_df.sort_values('ln_key').to_dict('records')
    except:
        return []

# --- 4. MAIN UI ---
st.set_page_config(layout="wide")

st.markdown("""
    <style>
        .stProgress > div > div > div > div {
            background-color: #39FF14;
            box-shadow: 0 0 10px #39FF14;
        }
    </style>
    """, unsafe_allow_html=True)

if 'last_count' not in st.session_state: st.session_state.last_count = 0

client = get_gspread_client()
if client:
    try:
        sheet = client.open(SHEET_NAME).sheet1
        
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour >= 13:
            curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
        else:
            curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
        prev_start, prev_end = curr_start - timedelta(days=1), curr_start

        current_sales = fetch_sales_data(sheet, curr_start)
        previous_sales = fetch_sales_data(sheet, prev_start, prev_end)
        
        display_count = len(current_sales)
        count_prev = len(previous_sales)

        if display_count > st.session_state.last_count and st.session_state.last_count > 0:
            trigger_sound("cha-ching.mp3")
        st.session_state.last_count = display_count

        # RENDERING
        st.markdown('<p style="font-size:40px; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom:-20px;">LIVE SALES TODAY</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; line-height:0.8; margin:0;">{display_count}</p>', unsafe_allow_html=True)
        
        st.progress(min(float(display_count) / float(DAILY_GOAL), 1.0))
        st.markdown(f"<center><b style='color:#39FF14; font-size:25px;'>Goal Progress: {display_count}/{DAILY_GOAL}</b></center>", unsafe_allow_html=True)
        
        st.markdown(f'<p style="font-size:45px; color:#888888; text-align:center; font-weight:bold; margin-bottom:0;">Yesterday: {count_prev}</p>', unsafe_allow_html=True)
        now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
        st.markdown(f'<p style="font-size:16px; text-align:center; color:#666666; margin-top:0;">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

        st.divider()
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<h3 style='color: white;'>New Sales:</h3>", unsafe_allow_html=True)
            for s in current_sales: 
                st.markdown(f"<span style='color: white;'>✔ {s['name']}</span>", unsafe_allow_html=True)
        with c2:
            st.markdown("<h3 style='color: #888888;'>Yesterday's Sales:</h3>", unsafe_allow_html=True)
            for s in previous_sales: 
                st.markdown(f"<span style='color: #888888;'>• {s['name']}</span>", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Display Error: {e}")
else:
    st.error("Google Auth Failed.")

time.sleep(60)
st.rerun()
