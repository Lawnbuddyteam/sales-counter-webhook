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
        ghl_id = str(data.get('id', 'No ID'))
        
        # Log the incoming ID to Render logs for debugging
        print(f"Received Webhook for ID: {ghl_id}")

        # Fetch only the ID column to check for duplicates
        # Using col_values is slower but more accurate if the sheet is small
        existing_ids = sheet.col_values(1) 
        
        if ghl_id in existing_ids:
            print(f"ID {ghl_id} already exists. Skipping.")
            return jsonify({"status": "ignored"}), 200

        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        # Force the append to the very next available row
        sheet.append_row([ghl_id, timestamp, full_name])
        print(f"Successfully added {full_name} to sheet.")
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return jsonify({"status": "error", "message": str(e)}), 200

    except Exception as e:
        # If Google Sheets is slow, we STILL return 200 to stop GHL from retrying
        print(f"Webhook Error: {e}")
        return jsonify({"status": "error_but_received", "details": str(e)}), 200

# --- 3. SERVER START ---
if __name__ == "__main__":
    # Render provides the port via an environment variable. 
    # This MUST be dynamic to pass the Port Scan.
    port = int(os.environ.get("PORT", 5000))
    
    # host='0.0.0.0' is required for Render to route external traffic
    app.run(host='0.0.0.0', port=port)
