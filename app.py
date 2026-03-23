import os
import json
from flask import Flask, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone

app = Flask(__name__)

# --- 1. AUTHENTICATION ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get('GCP_SERVICE_ACCOUNT')
    
    if creds_json:
        creds_info = json.loads(creds_json.strip())
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        
    return gspread.authorize(creds)

# Initialize sheet at startup
try:
    client = get_gspread_client()
    sheet = client.open("Sales_Counter").sheet1
except Exception as e:
    print(f"Failed to connect to Google Sheets: {e}")

# --- 2. THE WEBHOOK HANDLER (FIXED FOR 408) ---
@app.route('/ghl-webhook', methods=['POST'])
def handle_webhook():
    try:
        data = request.json
        # GHL can send 'id' or 'contact_id'. We check both.
        ghl_id = str(data.get('id') or data.get('contact_id') or 'Missing_ID')
        
        # 1. Fetch IDs from Column A
        all_ids = sheet.col_values(1) 
        
        # 2. Skip headers (Row 1) and check for actual duplicates
        # We start check from index 1 to ignore the 'ID' header in Row 1
        existing_ids = [str(i) for i in all_ids[1:]] 
        
        if ghl_id in existing_ids and ghl_id != 'Missing_ID':
            print(f"Verified Duplicate: {ghl_id} found. Skipping.")
            return jsonify({"status": "ignored"}), 200

        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "Unknown"
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        # Append to Col A (ID), Col B (Timestamp), Col C (Name)
        sheet.append_row([ghl_id, timestamp, full_name])
        print(f"Successfully added: {full_name}")
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error_but_received"}), 200

# --- 3. SERVER START ---
if __name__ == "__main__":
    # Render provides the port via an environment variable. 
    # This MUST be dynamic to pass the Port Scan.
    port = int(os.environ.get("PORT", 5000))
    
    # host='0.0.0.0' is required for Render to route external traffic
    app.run(host='0.0.0.0', port=port)
