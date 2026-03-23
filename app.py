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
    # 1. Immediately acknowledge the data
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    # 2. Process data quickly
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    full_name = f"{first_name} {last_name}".strip() or "Unknown Name"
    ghl_id = str(data.get('id', 'No ID'))
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    # 3. Post to Google Sheets
    try:
        # Re-authorize if the connection has timed out
        sheet.append_row([ghl_id, timestamp, full_name])
        return jsonify({"status": "success"}), 200
    except Exception as e:
        # Log the error but don't let the response hang
        print(f"Google Sheets Error: {e}")
        return jsonify({"status": "partial_success", "error": str(e)}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
