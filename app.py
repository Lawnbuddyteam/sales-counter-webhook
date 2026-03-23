import os
import json
from flask import Flask, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone

app = Flask(__name__)

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Look for the Environment Variable in Render
    creds_json = os.environ.get('GCP_SERVICE_ACCOUNT')
    
    if creds_json:
        creds_info = json.loads(creds_json.strip())
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    else:
        # Local fallback only
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        
    return gspread.authorize(creds)

# Initialize sheet once at startup
try:
    client = get_gspread_client()
    sheet = client.open("Sales_Counter").sheet1
except Exception as e:
    print(f"Failed to connect to Google Sheets: {e}")

@app.route('/ghl-webhook', methods=['POST'])
def handle_webhook():
    try:
        data = request.json
        ghl_id = str(data.get('id', 'No ID'))
        
        # --- OPTIMIZED DEDUPLICATION ---
        # Instead of fetching the WHOLE column, we fetch only the last 100 rows
        # This prevents the 408 timeout as the sheet grows
        last_rows = sheet.get_all_values()[-100:]
        existing_ids = [row[0] for row in last_rows] # IDs are in Column A (index 0)
        
        if ghl_id in existing_ids:
            return jsonify({"status": "ignored", "message": "Duplicate ID"}), 200
        # -------------------------------

        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip() or "Unknown Name"
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        # Standard append_row to the bottom
        sheet.append_row([ghl_id, timestamp, full_name])
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        # If Google Sheets is slow, we still return 200 to GHL to stop the timeout retries
        print(f"Webhook Error: {e}")
        return jsonify({"status": "error_but_received", "details": str(e)}), 200
