from flask import Flask, request, jsonify
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
LOG_FILE = "sales_log.csv"

# Initialize log file if it doesn't exist
if not os.path.exists(LOG_FILE):
    pd.DataFrame(columns=['id', 'timestamp', 'name']).to_csv(LOG_FILE, index=False)

@app.route('/ghl-webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    contact_id = data.get('id')
    first_name = data.get('first_name', 'Unknown')
    last_name = data.get('last_name', 'Unknown')
    full_name = f"{first_name} {last_name}"
    
    # Capture current time in UTC
    timestamp = datetime.utcnow().isoformat()

    # Save to local CSV
    new_sale = pd.DataFrame([[contact_id, timestamp, full_name]], columns=['id', 'timestamp', 'name'])
    new_sale.to_csv(LOG_FILE, mode='a', header=False, index=False)
    
    print(f"✅ Sale Recorded: {full_name}")
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    # Run on port 5000
    app.run(host='0.0.0.0', port=5000)
