import gspread
import json
import requests
import os
import tempfile
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from flask import jsonify # Kept for potential local testing/response handling

# Load environment variables (used if running locally, ignored by Cloud Function)
load_dotenv()

# --- CONFIGURATION (Reads from Environment Variables) ---
# WhatsApp API Configuration
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
API_BASE_URL = "https://waba.mysyncro.com/APIINFO/v22.0" 
API_URL = f"{API_BASE_URL}/{PHONE_NUMBER_ID}/messages"

# Note: SHEET_ID, WORKSHEET_NAME, and GOOGLE_CREDENTIALS are NO LONGER needed 
# by this script, as GAS sends the data directly.

# --- JSON PAYLOAD CONSTRUCTION (Remains mostly the same) ---

def build_whatsapp_payload(record):
    """
    Constructs the complex WhatsApp JSON payload using data received from the webhook.
    """
    
    # NOTE: Keys MUST match the keys sent by the Google Apps Script (headers).
    mobile_no = str(record.get('Mobile No', '')).replace(' ', '')
    application_id = str(record.get('Application ID', ''))
    applicant_name = str(record.get('Applicant Name', ''))
    application_type = str(record.get('Application Type (Certificate Name)', ''))

    if not mobile_no or not application_id:
        print("Missing required fields for JSON payload.")
        return None
        
    certificate_text = (
        f"{application_type}. Here is your certificate: "
        f"https://mahainformatics.com/files/kurla/{application_id}.pdf"
    )

    to_number = "91" + mobile_no

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "certsend",
            "language": {
                "code": "en"
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": application_id},
                        {"type": "text", "text": certificate_text}
                    ]
                }
            ]
        }
    }


# --- WEBHOOK ENTRY POINT ---

def process_sheet_change(request):
    """
    Receives webhook data from Google Apps Script containing the changed row data.
    This function will be the entry point for your Cloud Function or Flask server.
    """
    
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        print("FATAL ERROR: WhatsApp tokens (ACCESS_TOKEN or PHONE_NUMBER_ID) are missing.")
        return jsonify({"status": "error", "message": "Server configuration missing API credentials."}), 500

    try:
        # Get the JSON data sent from the Google Apps Script
        webhook_data = request.get_json(silent=True)
        
        if not webhook_data or 'new_row_data' not in webhook_data:
            print("ERROR: Invalid webhook data received.")
            return jsonify({"status": "error", "message": "Invalid webhook data structure."}), 400

        # The data we need is the single row dictionary sent by GAS
        row_data = webhook_data['new_row_data']
        row_index = webhook_data.get('row_index', 'N/A')
        
        print(f"\n--- Webhook received for Row {row_index} ---")
        print(f"Data: {row_data}")
        
        # 1. Build Payload
        payload = build_whatsapp_payload(row_data)
        
        if payload is None:
            return jsonify({"status": "error", "message": "Failed to construct payload (missing required data)."}), 400

        # 2. Send Message
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        response = requests.post(API_URL, headers=headers, json=payload)
        
        status_code = response.status_code

        if status_code in [200, 201, 202]:
            print(f"SUCCESS: Message sent for ID {row_data.get('Application ID')}. Status: {status_code}")
            return jsonify({"status": "success", "message": f"Message sent for row {row_index}"}), 200
        else:
            print(f"FAILURE: WhatsApp API Error {status_code}. Response: {response.text}")
            return jsonify({"status": "failure", "message": f"WhatsApp API failed: {status_code}"}), status_code

    except Exception as e:
        print(f"CRITICAL ERROR in webhook processing: {e}")
        return jsonify({"status": "error", "message": f"Internal server error: {e}"}), 500


if __name__ == '__main__':
    # This block is not used for the webhook flow; it's here for local testing setup.
    print("This script is now an HTTP trigger, run it via a web server/Cloud Function.")
    # You would typically wrap process_sheet_change in a Flask app if running locally:
    # app.run(debug=True, port=5000) 
    pass