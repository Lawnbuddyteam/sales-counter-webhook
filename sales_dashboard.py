import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
import time

# --- CONFIGURATION ---
API_KEY = "pit-0009ad29-406d-419f-910f-1b539d7ce0e6" 
LOCATION_ID = "snQISHLOuYGlR3jXbGU3"
DAILY_GOAL = 35

HEADERS = {
    'Authorization': f'Bearer {API_KEY}',
    'Version': '2021-07-28',
    'Content-Type': 'application/json'
}

TARGET_TAGS = ["00490 - card updated", "pre pay quote won", "950 - credit card information"]
EXCLUDE_TAG = "client"

st.set_page_config(page_title="Live Sales Counter", layout="wide")

# --- DATA FETCHING LOGIC ---
def get_sales_day_bounds():
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour < 14:
        curr_start = now_utc.replace(hour=14, minute=0, second=0, microsecond=0) - timedelta(days=1)
    else:
        curr_start = now_utc.replace(hour=14, minute=0, second=0, microsecond=0)
    
    prev_start = curr_start - timedelta(days=1)
    return curr_start, prev_start, curr_start 

def get_local_sales(start_time, end_time=None):
    """
    Reads sales from Google Sheets and filters by the time the WEBHOOK was received,
    not when the GHL contact was last modified.
    """
    try:
        # Pull all data from the sheet
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Convert timestamp to proper UTC datetime
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC')
        
        # Filter for the specific sales window (9am EST to 9am EST)
        if end_time:
            mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time)
        else:
            mask = (df['timestamp'] >= start_time)
            
        filtered_df = df[mask].copy()
        
        # Sort Alphabetically by Last Name
        def get_last_name(name):
            parts = str(name).split()
            return parts[-1].lower() if len(parts) > 1 else str(name).lower()
            
        filtered_df['last_name_sort'] = filtered_df['name'].apply(get_last_name)
        return filtered_df.sort_values('last_name_sort')
    except Exception as e:
        return pd.DataFrame()

# --- INITIAL DATA PULL ---
curr_start, prev_start, prev_end = get_sales_day_bounds()
current_sales, _ = fetch_sales_data(curr_start)
previous_sales, _ = fetch_sales_data(prev_start, prev_end)
count_curr = len(current_sales)

# --- DYNAMIC STYLING ---
bg_color = "#FFD700" if count_curr >= DAILY_GOAL else "#F5F5F5"
text_color = "#111111" if count_curr >= DAILY_GOAL else "#2E7D32"

st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg_color}; transition: background-color 2s ease; }}
    .big-font {{ font-size:350px !important; font-weight: bold; color: {text_color}; text-align: center; line-height: 0.8; margin: 0px; }}
    .prev-font {{ font-size:60px !important; color: #555555; text-align: center; margin-top: 20px; }}
    .label-font {{ font-size:40px !important; text-align: center; color: #1F4E78; margin-bottom: 0px; }}
    .update-font {{ font-size:18px !important; text-align: center; color: #666666; margin-top: 10px; }}
    .stProgress > div > div > div > div {{ background-color: #2E7D32; }}
    </style>
    """, unsafe_allow_html=True)

st.markdown('<p class="label-font">LIVE SALES TODAY</p>', unsafe_allow_html=True)

main_container = st.empty()
progress_container = st.empty()
prev_container = st.empty()
update_time_container = st.empty()

st.divider()
test_mode = st.checkbox("Show Detail Audit Lists", value=True)
dup_warning = st.empty()
col1, col2 = st.columns(2)
debug_curr = col1.empty()
debug_prev = col2.empty()

# --- UPDATE LOOP ---
# --- DASHBOARD UI ---
while True:
    curr_start, prev_start, prev_end = get_sales_day_bounds()
    df_curr = get_local_sales(curr_start)
    df_prev = get_local_sales(prev_start, prev_end)
    
    count_curr = len(df_curr)
    count_prev = len(df_prev)

    # DYNAMIC BACKGROUND: Shifts to Gold at 35
    bg_color = "#FFD700" if count_curr >= DAILY_GOAL else "#F5F5F5"
    st.markdown(f"""<style>.stApp {{ background-color: {bg_color}; transition: 2s; }}</style>""", unsafe_allow_html=True)

    # Header & Massive Number
    st.markdown('<p class="label-font">SALES TODAY</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="big-font">{count_curr}</p>', unsafe_allow_html=True)
    
    # Progress Bar
    progress = min(count_curr / DAILY_GOAL, 1.0)
    st.progress(progress)
    st.markdown(f"<center><b>Goal: {count_curr} / {DAILY_GOAL}</b></center>", unsafe_allow_html=True)

    # Yesterday Stats & Clock
    st.markdown(f'<p class="prev-font">Yesterday: {count_prev}</p>', unsafe_allow_html=True)
    now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
    st.markdown(f'<p class="update-font">Last Update: {now_est} EST</p>', unsafe_allow_html=True)

    # Alphabetical Audit Lists
    if st.checkbox("Show Audit Lists", value=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write("### Today (A-Z)")
            st.success("  \n".join([f"✔ {n}" for n in df_curr['name']]) if not df_curr.empty else "Waiting for sales...")
        with col2:
            st.write("### Yesterday (A-Z)")
            st.warning("  \n".join([f"✔ {n}" for n in df_prev['name']]) if not df_prev.empty else "No sales recorded.")

    if count_curr >= DAILY_GOAL:
        st.balloons()
        st.success("🔥 DAILY GOAL REACHED! 🔥")

    time.sleep(30) # iPad refreshes every 30 seconds
    st.rerun()
