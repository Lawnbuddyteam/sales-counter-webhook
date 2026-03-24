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

# Pull GHL Key
GHL_API_KEY = os.environ.get('GHL_API_KEY')

# --- 2. GOOGLE AUTH (MANUAL REBUILD) ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # Rebuild the JSON structure from individual Render variables
        creds_dict = {
            "type": os.environ.get("type", "service_account"),
            "project_id": os.environ.get("project_id"),
            "private_key_id": os.environ.get("private_key_id"),
            "private_key": os.environ.get("private_key").replace('\\n', '\n'),
            "client_email": os.environ.get("client_email"),
            "client_id": os.environ.get("client_id"),
            "auth_uri": os.environ.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": os.environ.get("token_uri", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": os.environ.get("auth_provider_x509_cert_url"),
            "client_x509_cert_url": os.environ.get("client_x509_cert_url")
        }
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Auth Rebuild Failed: {e}")
        return None

# --- 3. GHL FETCH ---
def get_live_ghl_count():
    if not GHL_API_KEY:
        return 0, "Missing GHL_API_KEY in Render"
    
    now_utc = datetime.now(timezone.utc)
    # 9 AM EST = 13:00 UTC
    start_time = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
    if now_utc.hour < 13: start_time -= timedelta(days=1)

    url = "https://services.leadconnectorhq.com/contacts/search"
    headers = {
        "Authorization": f"Bearer {GHL_API_KEY.strip()}",
        "Version": "2021-04-15",
        "Content-Type": "application/json"
    }
    payload = {
        "locationId": LOCATION_ID,
        "pageLimit": 100,
        "filters": [{"field": "updatedAt", "operator": "gte", "value": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")}]
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code != 200: return 0, f"GHL Error {r.status_code}"
        
        contacts = r.json().get('contacts', [])
        count = 0
        for c in contacts:
            if "client" in [t.lower() for t in c.get('tags', [])]:
                upd = c.get('updatedAt', '').replace('Z', '+00:00')
                if upd and datetime.fromisoformat(upd) >= start_time:
                    count += 1
        return count, "OK"
    except: return 0, "GHL Conn Timeout"

# --- 4. DATA PROCESSING ---
def fetch_sales_data(sheet, start_time, end_time=None):
    try:
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] < (end_time if end_time else datetime.now(timezone.utc) + timedelta(days=1)))
        return df[mask].drop_duplicates(subset=['name']).to_dict('records')
    except: return []

# --- 5. MAIN UI ---
st.set_page_config(page_title="Sales Dashboard", layout="wide")

client = get_gspread_client()
if client:
    try:
        sheet = client.open(SHEET_NAME).sheet1
        
        # Time Windows
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour >= 13:
            curr_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
        else:
            curr_start = (now_utc - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
        prev_start, prev_end = curr_start - timedelta(days=1), curr_start

        # Counts
        count_curr, status = get_live_ghl_count()
        current_sales = fetch_sales_data(sheet, curr_start)
        previous_sales = fetch_sales_data(sheet, prev_start, prev_end)

        # Big Display
        st.markdown(f'<p style="font-size:350px; text-align:center; color:white; font-weight:900; margin:0;">{count_curr}</p>', unsafe_allow_html=True)
        st.progress(min(count_curr/DAILY_GOAL, 1.0))

        c1, c2 = st.columns(2)
        c1.metric("Today (Sheet)", len(current_sales))
        c2.metric("Yesterday (Sheet)", len(previous_sales))
        
        if status != "OK": st.warning(f"Status: {status}")

    except Exception as e:
        st.error(f"Sheet Error: {e}")
else:
    st.error("Waiting for Google Authorization...")

time.sleep(60)
st.rerun()
