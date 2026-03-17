import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import time
import json

# --- 1. CONFIGURATION ---
DAILY_GOAL = 55
SHEET_NAME = "Sales_Counter" 

# --- 2. AUTHENTICATION ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_info = json.loads(st.secrets["gcp_service_account"].strip())
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 Auth Failed: {e}")
        st.stop()

# Initialize Sheet Connection
client = get_gspread_client()
sheet = client.open(SHEET_NAME).sheet1

# --- 3. FUNCTION DEFINITIONS ---

def fetch_sales_data(start_time, end_time=None):
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return [], "Success"
        
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC')
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time) if end_time else (df['timestamp'] >= start_time)
        
        filtered_df = df[mask].copy()
        filtered_df['last_name_sort'] = filtered_df['name'].apply(lambda x: str(x).split()[-1].lower() if len(str(x).split()) > 1 else str(x).lower())
        return filtered_df.sort_values('last_name_sort').to_dict('records'), "Success"
    except:
        return [], "Error"

def get_sales_day_bounds():
    now_utc = datetime.now(timezone.utc)
    curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
    if now_utc.hour < 13: curr_start -= timedelta(days=1)
    return curr_start, curr_start - timedelta(days=1), curr_start

def apply_custom_styles(current_count):
    bg_color = "#0E1117" 
    text_color = "#39FF14" if current_count >= DAILY_GOAL else "#FFFFFF"
    glow = "0 0 20px #39FF14, 0 0 40px #39FF14" if current_count >= DAILY_GOAL else "none"
    
    st.markdown(f"""
        <style>
        .stApp {{ background-color: {bg_color}; }}
        .big-font {{ 
            font-size:320px !important; font-weight: 900; color: {text_color}; 
            text-align: center; line-height: 0.8; margin: 0px; text-shadow: {glow};
            font-family: 'Helvetica Neue', sans-serif;
        }}
        .prev-font {{ font-size:45px !important; color: #888888; text-align: center; margin-top: 15px; font-weight:bold; }}
        .label-font {{ font-size:40px !important; text-align: center; color: #5D9CEC; font-weight: bold; margin-bottom: -20px; }}
        .update-font {{ font-size:14px !important; text-align: center; color: #444444; margin-top: 10px; }}
        .stProgress > div > div > div > div {{ background-image: linear-gradient(to right, #1B5E20, #39FF14); }}
        </style>
        """, unsafe_allow_html=True)

# --- 4. MAIN DASHBOARD LOOP ---

if 'celebrated' not in st.session_state:
    st.session_state.celebrated = False

st.markdown('<p class="label-font">LIVE SALES TODAY</p>', unsafe_allow_html=True)

main_container = st.empty()
progress_container = st.empty()
prev_container = st.empty()
update_time_container = st.empty()

st.divider()
test_mode = st.checkbox("Show Audit Lists", value=True)
col1, col2 = st.columns(2)
debug_curr = col1.empty()
debug_prev = col2.empty()

while True:
    curr_start, prev_start, prev_end = get_sales_day_bounds()
    current_sales, _ = fetch_sales_data(curr_start)
    previous_sales, _ = fetch_sales_data(prev_start, prev_end)
    
    count_curr = len(current_sales)
    count_prev = len(previous_sales)
    
    apply_custom_styles(count_curr)
    
    # Update Celebration
    if count_curr >= DAILY_GOAL and not st.session_state.celebrated:
        st.balloons()
        st.session_state.celebrated = True
    elif count_curr < DAILY_GOAL:
        st.session_state.celebrated = False

    main_container.markdown(f'<p class="big-font">{count_curr}</p>', unsafe_allow_html=True)
    
    progress_val = min(float(count_curr) / float(DAILY_GOAL), 1.0)
    with progress_container:
        st.write("")
        st.progress(progress_val)
        label_col = "#39FF14" if count_curr >= DAILY_GOAL else "#5D9CEC"
        st.markdown(f"<center><b style='color:{label_col}; font-size:25px;'>Goal Progress: {count_curr} / {DAILY_GOAL}</b></center>", unsafe_allow_html=True)

    prev_container.markdown(f'<p class="prev-font">Yesterday: {count_prev}</p>', unsafe_allow_html=True)

    now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
    update_time_container.markdown(f'<p class="update-font">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

    if test_mode:
        with debug_curr:
            st.markdown("<h3 style='color: #5D9CEC;'>Today (A-Z)</h3>", unsafe_allow_html=True)
            if current_sales:
                st.markdown("  \n".join([f"<span style='color:white; font-size:18px;'>✔ {c['name']}</span>" for c in current_sales]), unsafe_allow_html=True)
            else:
                st.info("Waiting for first sale...")
        with debug_prev:
            st.markdown("<h3 style='color: #888888;'>Yesterday (A-Z)</h3>", unsafe_allow_html=True)
            if previous_sales:
                st.markdown("  \n".join([f"<span style='color:#888888; font-size:18px;'>✔ {c['name']}</span>" for c in previous_sales]), unsafe_allow_html=True)
            else:
                st.info("No data for yesterday.")

    time.sleep(60)
    st.rerun()
