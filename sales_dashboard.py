import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- GOOGLE SHEETS AUTHENTICATION ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" in st.secrets:
        try:
            # We strip any accidental whitespace from the secret before loading
            raw_json = st.secrets["gcp_service_account"].strip()
            creds_info = json.loads(raw_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        except json.JSONDecodeError as e:
            st.error(f"❌ Secret Formatting Error: {e}")
            st.stop()
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        
    return gspread.authorize(creds)

# Initialize the client and sheet
client = get_gspread_client()
sheet = client.open("Sales_Counter").sheet1

st.set_page_config(page_title="Live Sales Counter", layout="wide")

# --- 2. DATA FETCHING FUNCTION ---
def fetch_sales_data(start_time, end_time=None):
    """
    Queries Google Sheets for sales and filters by the webhook timestamp.
    """
    try:
        # Pull all data from the sheet
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return [], "Success (No data)"
            
        # Convert timestamp to proper UTC datetime
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC')
        
        # Filter for the specific sales window (14:00 UTC / 9am EST)
        if end_time:
            mask = (df['timestamp'] >= start_time) & (df['timestamp'] < end_time)
        else:
            mask = (df['timestamp'] >= start_time)
            
        filtered_df = df[mask].copy()
        
        # Sort Alphabetically by Last Name safely
        def get_last_name(name):
            parts = str(name).split()
            # Returns last word lowercased, or the whole name if single word
            return parts[-1].lower() if len(parts) > 1 else str(name).lower()
            
        filtered_df['last_name_sort'] = filtered_df['name'].apply(get_last_name)
        sorted_df = filtered_df.sort_values('last_name_sort')
        
        return sorted_df.to_dict('records'), "Success"
    except Exception as e:
        return [], str(e)

def get_sales_day_bounds():
    """Calculates the 14:00 UTC (9am EST) reset windows."""
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour < 14:
        curr_start = now_utc.replace(hour=14, minute=0, second=0, microsecond=0) - timedelta(days=1)
    else:
        curr_start = now_utc.replace(hour=14, minute=0, second=0, microsecond=0)
    
    prev_start = curr_start - timedelta(days=1)
    return curr_start, prev_start, curr_start 

# --- 3. DYNAMIC UI & STYLING ---
def apply_custom_styles(current_count):
    # Background turns Gold (#FFD700) when goal is hit
    bg_color = "#FFD700" if current_count >= DAILY_GOAL else "#F5F5F5"
    text_color = "#111111" if current_count >= DAILY_GOAL else "#2E7D32"
    
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

# --- 4. MAIN DASHBOARD LOOP ---
st.markdown('<p class="label-font">LIVE SALES TODAY</p>', unsafe_allow_html=True)

main_container = st.empty()
progress_container = st.empty()
prev_container = st.empty()
update_time_container = st.empty()
dup_warning = st.empty()

st.divider()
test_mode = st.checkbox("Show Detail Audit Lists", value=True)
col1, col2 = st.columns(2)
debug_curr = col1.empty()
debug_prev = col2.empty()

while True:
    curr_start, prev_start, prev_end = get_sales_day_bounds()
    
    current_sales, curr_status = fetch_sales_data(curr_start)
    previous_sales, prev_status = fetch_sales_data(prev_start, prev_end)
    
    count_curr = len(current_sales)
    count_prev = len(previous_sales)
    
    # Apply styling based on current count
    apply_custom_styles(count_curr)
    
    # Check for Duplicates (IDs that appear in both lists)
    curr_ids = {str(c.get('id')) for c in current_sales}
    prev_ids = {str(c.get('id')) for c in previous_sales}
    duplicates = curr_ids.intersection(prev_ids)

    # Update Main Display
    main_container.markdown(f'<p class="big-font">{count_curr}</p>', unsafe_allow_html=True)
    
    # Update Progress Bar
    progress = min(count_curr / DAILY_GOAL, 1.0)
    with progress_container:
        st.progress(progress)
        st.markdown(f"<center><b>Goal Progress: {count_curr} / {DAILY_GOAL}</b></center>", unsafe_allow_html=True)

    # Yesterday Stats
    prev_container.markdown(f'<p class="prev-font">Yesterday: {count_prev}</p>', unsafe_allow_html=True)

    # Clock (EST is UTC-4)
    now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
    update_time_container.markdown(f'<p class="update-font">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

    # Duplicate Warning
    if duplicates:
        dup_warning.error(f"⚠️ DUPLICATE DETECTED: {len(duplicates)} contact(s) on both lists.")
    else:
        dup_warning.empty()

    # Audit Lists
    if test_mode:
        with debug_curr:
            st.write("### Today's Sales (A-Z)")
            if current_sales:
                curr_text = ""
                for c in current_sales:
                    marker = "🚨" if str(c.get('id')) in duplicates else "✔"
                    curr_text += f"{marker} {c.get('name', 'Unknown')}  \n"
                st.success(curr_text)
            else:
                st.info("No sales recorded since 9am.")

        with debug_prev:
            st.write("### Yesterday's Sales (A-Z)")
            if previous_sales:
                prev_text = ""
                for c in previous_sales:
                    marker = "🚨" if str(c.get('id')) in duplicates else "✔"
                    prev_text += f"{marker} {c.get('name', 'Unknown')}  \n"
                st.warning(prev_text)
            else:
                st.info("No sales found for yesterday.")

    if count_curr >= DAILY_GOAL:
        st.balloons()

    time.sleep(60)
    st.rerun()
