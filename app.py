import os
import gspread
from flask import Flask, request, jsonify
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# You will store your credentials as a "Secret" in Render or in a file
creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Sales_Counter").sheet1

@app.route('/ghl-webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    first_name = data.get('first_name', 'Unknown')
    last_name = data.get('last_name', 'Unknown')
    full_name = f"{first_name} {last_name}"
    timestamp = datetime.utcnow().isoformat()
    
    # Append the row to Google Sheets
    sheet.append_row([data.get('id'), timestamp, full_name])
    
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
