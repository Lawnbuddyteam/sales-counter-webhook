import os
import json
from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Look for the Environment Variable we just created
    creds_json = os.environ.get('GCP_SERVICE_ACCOUNT')
    
    if creds_json:
        creds_info = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    else:
        # Fallback for local testing only
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
        
    return gspread.authorize(creds)

# Connect to the sheet
client = get_gspread_client()
sheet = client.open("Sales_Counter").sheet1

@app.route('/ghl-webhook', methods=['POST'])
def handle_webhook():
    try:
        data = request.json
        # Append: Name, ID, Current Time
        sheet.append_row([
            data.get('name', 'Unknown'),
            str(data.get('id', 'No ID')),
            datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        ])
        return "Success", 200
    except Exception as e:
        print(f"Error: {e}")
        return str(e), 500
