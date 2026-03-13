import os
import json
from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone

app = Flask(__name__)

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get('GCP_SERVICE_ACCOUNT')
    
    if creds_json:
        creds_info = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    else:
        # For local testing if you have the file
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        
    return gspread.authorize(creds)

# Initialize sheet
client = get_gspread_client()
sheet = client.open("Sales_Counter").sheet1

@app.route('/ghl-webhook', methods=['POST'])
def handle_webhook():
    try:
        data = request.json
        # These lines MUST be indented under the 'def'
        sheet.append_row([
            data.get('name', 'Unknown'),
            str(data.get('id', 'No ID')),
            datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        ])
        return "Success", 200
    except Exception as e:
        print(f"Error: {e}")
        return str(e), 500

if __name__ == "__main__":
    # This part is for local testing; Render uses Gunicorn
    app.run(host='0.0.0.0', port=5000)
