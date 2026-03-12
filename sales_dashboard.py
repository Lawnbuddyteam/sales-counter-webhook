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

def fetch_sales_data(start_time, end_time=None):
    url = "https://services.leadconnectorhq.com/contacts/search"
    all_contacts = []
    status_msg = "Success"

    for tag in TARGET_TAGS:
        payload = {
            "locationId": LOCATION_ID, 
            "filters": [{"field": "tags", "operator": "eq", "value": tag}],
            "pageLimit": 400 
        }
        try:
            response = requests.post(url, json=payload, headers=HEADERS)
            if response.status_code == 200:
                contacts = response.json().get('contacts', [])
                all_contacts.extend(contacts)
            else:
                status_msg = f"Error {response.status_code}"
        except:
            status_msg = "Connection Error"

    valid_ids = set()
    final_list = []
    
    for contact in all_contacts:
        c_id = contact.get('id')
        if not c_id or c_id in valid_ids: continue
        
        tags = [t.lower().strip() for t in contact.get('tags', []) if t]
        if EXCLUDE_TAG.lower() in tags: continue
        
        updated_str = contact.get('dateUpdated', contact.get('updatedAt'))
        if not updated_str: continue
        
        updated_dt = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))

        if end_time:
            if start_time <= updated_dt < end_time:
                final_list.append(contact)
                valid_ids.add(c_id)
        else:
            if updated_dt >= start_time:
                final_list.append(contact)
                valid_ids.add(c_id)
                
    # FIXED: Sorting logic to handle None values in lastName
    def get_sort_key(x):
        ln = x.get('lastName')
        return ln.lower() if ln else ""

    final_list.sort(key=get_sort_key)
    
    return final_list, status_msg

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
while True:
    curr_start, prev_start, prev_end = get_sales_day_bounds()
    current_sales, _ = fetch_sales_data(curr_start)
    previous_sales, _ = fetch_sales_data(prev_start, prev_end)
    
    count_curr = len(current_sales)
    count_prev = len(previous_sales)
    
    # Check for Duplicates
    curr_ids = {c.get('id') for c in current_sales}
    prev_ids = {c.get('id') for c in previous_sales}
    duplicates = curr_ids.intersection(prev_ids)
    
    # Display Display
    main_container.markdown(f'<p class="big-font">{count_curr}</p>', unsafe_allow_html=True)
    progress = min(count_curr / DAILY_GOAL, 1.0)
    with progress_container:
        st.progress(progress)
        st.markdown(f"<center><b>Goal Progress: {count_curr} / {DAILY_GOAL}</b></center>", unsafe_allow_html=True)
    prev_container.markdown(f'<p class="prev-font">Yesterday: {count_prev}</p>', unsafe_allow_html=True)
    now_est = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime('%I:%M:%S %p')
    update_time_container.markdown(f'<p class="update-font">Last Updated: {now_est} EST</p>', unsafe_allow_html=True)

    # Duplicate Warning Note
    if duplicates:
        dup_warning.error(f"⚠️ DUPLICATE DETECTED: {len(duplicates)} contact(s) appear on both lists. Verify if tags were updated twice.")
    else:
        dup_warning.empty()

    if test_mode:
        with debug_curr:
            st.write("### Today's Sales (A-Z)")
            if current_sales:
                curr_details = ""
                for c in current_sales:
                    marker = "🚨" if c.get('id') in duplicates else "✔"
                    curr_details += f"{marker} {c.get('firstName', '')} {c.get('lastName', 'Unknown')}  \n"
                st.success(curr_details)
            else:
                st.info("No sales detected yet.")

        with debug_prev:
            st.write("### Yesterday's Sales (A-Z)")
            if previous_sales:
                prev_details = ""
                for c in previous_sales:
                    marker = "🚨" if c.get('id') in duplicates else "✔"
                    prev_details += f"{marker} {c.get('firstName', '')} {c.get('lastName', 'Unknown')}  \n"
                st.warning(prev_details)
            else:
                st.info("No sales found for yesterday.")

    if count_curr >= DAILY_GOAL:
        st.balloons()

    time.sleep(60)
    st.rerun()
