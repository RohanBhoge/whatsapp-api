import gspread
import json
import requests
import os
import tempfile
from flask import Flask, jsonify, request
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION (Reads from Render Environment Variables) ---
# This code is now configured to read sensitive information securely from environment variables 
# set up on the Render dashboard.

# Google Sheet Configuration
# os.getenv() retrieves the value; the second argument is a default/fallback value.
SPREADSHEET_NAME = os.getenv("SHEET_NAME", "My Product Inventory Sheet") 
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Products")

# Client API Configuration
CLIENT_API_ENDPOINT = os.getenv("CLIENT_API_ENDPOINT")
CLIENT_API_KEY = os.getenv("CLIENT_API_KEY") 

# Initialize Flask App
app = Flask(__name__)

# --- GOOGLE SHEETS DATA RETRIEVAL ---

def get_sheet_data():
    """
    Authenticates using GOOGLE_CREDENTIALS env var, fetches all records, 
    and deletes the temporary credentials file afterward.
    """
    
    # 1. Get the JSON content from the secure environment variable
    creds_json_content = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json_content:
        print("FATAL ERROR: GOOGLE_CREDENTIALS environment variable not set. Cannot authenticate to Google Sheets.")
        return None
        
    tmp_file_name = None
    data_records = None

    try:
        # 2. Write the JSON content to a temporary file, as gspread/ServiceAccountCredentials requires a file path
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
            tmp_file.write(creds_json_content)
            tmp_file_name = tmp_file.name

        # 3. Define the scope and authenticate
        scope = [
            "https://spreadsheets.google.com/feeds", 
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(tmp_file_name, scope)
        client = gspread.authorize(creds)
        
        # 4. Open the spreadsheet and worksheet
        sheet = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME) 

        # 5. Get all records
        data_records = sheet.get_all_records() 
        
        return data_records

    except gspread.exceptions.NoValidUrlKeyOrTitle:
        print(f"ERROR: Spreadsheet '{SPREADSHEET_NAME}' not found or sheet name is wrong.")
    except Exception as e:
        print(f"An unexpected error occurred during Sheets access: {e}")
    finally:
        # 6. CRUCIAL: Clean up and delete the temporary file immediately
        if tmp_file_name and os.path.exists(tmp_file_name):
            os.remove(tmp_file_name)
            
    return None

# --- JSON PAYLOAD CONSTRUCTION ---

def build_whatsapp_payload(record):
    """
    Constructs the complex WhatsApp JSON payload using data from a single sheet record.
    """
    
    # 1. Map fields from the Sheet data (using the column headers as keys)
    mobile_no = str(record.get('Mobile No', '')).replace(' ', '')
    application_id = str(record.get('Application ID', ''))
    applicant_name = str(record.get('Applicant Name', ''))
    application_type = str(record.get('Application Type (Certificate Name)', ''))

    # Basic validation
    if not mobile_no or not application_id:
        print(f"Skipping record due to missing required fields: {record}")
        return None
        
    # 2. Construct the exact nested JSON structure required
    return {
        "integrated_number": "919270334724",
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": "kurlaaa",
                "language": {
                    "code": "en",
                    "policy": "deterministic"
                },
                "namespace": "bef520bd_6b38_4231_8cd9_2f253f10a1dd",
                "to_and_components": [
                    {
                        "to": [
                            f"91{mobile_no}"
                        ],
                        "components": {
                            "header_1": {
                                "filename": application_id,
                                "type": "document",
                                "value": f"https://mahainformatics.com/files/andheri/{application_id}.pdf"
                            },
                            "body_1": {
                                "type": "text",
                                "value": f"Namaste🙏 {applicant_name} check your {application_type} certificate"
                            }
                        }
                    }
                ]
            }
        }
    }

# --- FLASK WEBHOOK ENDPOINT ---

@app.route('/sheet-update', methods=['POST'])
def handle_webhook():
    """
    Receives the webhook call from Google Apps Script, processes data, and sends it.
    """
    print("\n--- Webhook received from Google Sheets ---")
    
    # Basic validation of environment variables
    if not CLIENT_API_ENDPOINT or not CLIENT_API_KEY:
        print("FATAL ERROR: Client API secrets (ENDPOINT/KEY) are missing from environment variables.")
        return jsonify({"status": "error", "message": "Server configuration error."}), 500

    # Fetch all the latest data from the sheet
    data_records = get_sheet_data()
    
    if not data_records:
        return jsonify({"status": "error", "message": "Failed to retrieve data from Google Sheets."}), 500

    success_count = 0
    error_count = 0
    
    # Iterate through the sheet data and send a message for each record
    for record in data_records:
        payload = build_whatsapp_payload(record)
        
        if payload is None:
            error_count += 1
            continue

        json_to_send = json.dumps(payload)

        print(f"Attempting to send data for Mobile No: {record.get('Mobile No', 'N/A')}")
        
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {CLIENT_API_KEY}' 
            }
            
            # This is the actual call to your client's WhatsApp API
            response = requests.post(CLIENT_API_ENDPOINT, data=json_to_send, headers=headers)
            
            if response.status_code in [200, 201, 202]: 
                print(f"SUCCESS: Data sent for {record.get('Applicant Name')}. Status: {response.status_code}")
                success_count += 1
            else:
                print(f"FAILURE: Client API returned status {response.status_code} for {record.get('Applicant Name')}.")
                error_count += 1

        except requests.exceptions.RequestException as e:
            print(f"NETWORK ERROR: Failed to connect to Client API: {e}")
            error_count += 1

    # 4. Return a success response to the Google Apps Script webhook
    return jsonify({
        "status": "processing_complete",
        "message": "Sheet data fetched and processing initiated.",
        "records_processed": len(data_records),
        "records_sent_successfully": success_count,
        "records_failed": error_count
    }), 200
