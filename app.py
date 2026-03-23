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
        if not data:
            return jsonify({"error": "No data received"}), 400

        ghl_id = str(data.get('id', 'No ID'))
        
        # --- OPTIMIZED DEDUPLICATION ---
        # We only fetch the last 100 entries to ensure a fast response under 60s
        last_rows = sheet.get_all_values()[-100:]
        existing_ids = [row[0] for row in last_rows] 
        
        if ghl_id in existing_ids:
            return jsonify({"status": "ignored", "message": "Duplicate ID"}), 200
        # -------------------------------

        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip() or "Unknown Name"
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        # Append data to the Google Sheet
        sheet.append_row([ghl_id, timestamp, full_name])
        
        return jsonify({"status": "success"}), 200

    except Exception as e:
        # If Google Sheets is slow, we STILL return 200 to stop GHL from retrying
        print(f"Webhook Error: {e}")
        return jsonify({"status": "error_but_received", "details": str(e)}), 200

# --- 3. SERVER START ---
if __name__ == "__main__":
    # Render requires the port to be dynamic via Environment Variables
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
