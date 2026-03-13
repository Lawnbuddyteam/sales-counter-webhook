import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import time
import json

# --- 1. CONFIGURATION ---
DAILY_GOAL = 35
SHEET_NAME = "Sales_Counter" 

# --- 2. AUTHENTICATION (Laptop & iPad Compatible) ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            # Cloud/iPad Authentication
            creds_info = json.loads(st.secrets["gcp_service_account"].strip())
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        else:
            # Local Laptop Authentication
            creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 Authentication Failed: {e}")
        st.stop()

# Initialize Sheet Connection
try:
    client = get_gspread_client()
    sheet = client.open(SHEET_NAME).sheet1
except Exception as e:
    st.error(f"❌ Google API Error: Check Drive API and Sheet Sharing. Detail: {e}")
    st.stop()

# --- 3. FUNCTION DEFINITIONS ---

def fetch_sales_data(start_time, end_time=None):
    """Queries Google Sheets and filters by the webhook timestamp."""
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return [], "Success"
        
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC')
        
        if end_time:
            mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time)
        else:
            mask = (df['timestamp'] >= start_time)
            
        filtered_df = df[mask].copy()
        
        def get_last_name(name):
            parts = str(name).split()
            return parts[-1].lower() if len(parts) > 1 else str(name).lower()
            
        filtered_df['last_name_sort'] = filtered_df['name'].apply(get_last_name)
        sorted_df = filtered_df.sort_values('last_name_sort')
        return sorted_df.to_dict('records'), "Success"
    except Exception as e:
        return [], str(e)

def get_sales_day_bounds():
    """Calculates the 9am EST (14:00 UTC) reset windows."""
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour < 14:
        curr_start = now_utc.replace(hour=14, minute=0, second=0, microsecond=0) - timedelta(days=1)
    else:
        curr_start = now_utc.replace(hour=14, minute=0, second=0, microsecond=0)
    prev_start = curr_start - timedelta(days=1)
    return curr_start, prev_start, curr_start 

def apply_custom_styles(current_count):
    bg_color = "#FFD700" if current_count >= DAILY_GOAL else "#F5F5F5"
    text_color = "#111111" if current_count >= DAILY_GOAL else "#2E7D32"
    st.markdown(f"""
        <style>
        .stApp {{ background-color: {bg_color}; transition: background-color 2s ease; }}
        .big-font {{ font-size:300px !important; font-weight: bold; color: {text_color}; text-align: center; line-height: 0.8; margin: 0px; }}
        .prev-font {{ font-size:50px !important; color: #555555; text-align: center; margin-top: 20px; }}
        .label-font {{ font-size:40px !important; text-align: center; color: #1F4E78; margin-bottom: 0px; }}
        .update-font {{ font-size:18px !important; text-align: center; color: #666666; margin-top: 10px; }}
        </style>
        """, unsafe_allow_html=True)

# --- 4. MAIN DASHBOARD LOOP ---

st.markdown('<p class="label-font">LIVE SALES TODAY</p>', unsafe_allow_html=True)

main_container = st.empty()
progress_container = st.empty()
prev_container = st.empty()
update_time_container = st.empty()

st.divider()
test_mode = st.checkbox("Show Detail Audit Lists", value=True)
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
    
# Update Main Display
    main_container.markdown(f'<p class="big-font">{count_curr}</p>', unsafe_allow_html=True)
    
    # Force Progress Bar visibility even at 0
    progress = float(min(count_curr / DAILY_GOAL, 1.0))
    with progress_container:
        st.progress(progress)
        st.markdown(f"<center><b style='color:#1F4E78; font-size:20px;'>Goal Progress: {count_curr} / {DAILY_GOAL}</b></center>", unsafe_allow_html=True)

    prev_container.markdown(f'<p class="prev-font">Yesterday: {count_prev}</p>', unsafe_allow_html=True)

    now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
    update_time_container.markdown(f'<p class="update-font">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

    if test_mode:
        with debug_curr:
            st.write("### Today (A-Z)")
            if current_sales:
                st.success("  \n".join([f"✔ {c['name']}" for c in current_sales]))
            else:
                st.info("Waiting for first sale...")
        with debug_prev:
            st.write("### Yesterday (A-Z)")
            if previous_sales:
                st.warning("  \n".join([f"✔ {c['name']}" for c in previous_sales]))
            else:
                st.info("No data for yesterday.")

    if count_curr >= DAILY_GOAL:
        st.balloons()

    time.sleep(60)
    st.rerun()
