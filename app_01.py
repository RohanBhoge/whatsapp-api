import gspread
import json
import os
import tempfile
from flask import Flask, jsonify, request
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
load_dotenv()

SHEET_ID = os.getenv("SHEET_ID") 
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Data")

# Initialize Flask App
app = Flask(__name__)

# --- GOOGLE SHEETS DATA WRITING ---

def write_sheet_data(sheet_id, new_record):
    """
    Authenticates, opens the target sheet using its ID, and appends a new row.
    
    Args:
        sheet_id (str): The ID of the Google Spreadsheet.
        new_record (dict): Data to be written (keys must match column headers).
    """
    
    creds_json_content = os.getenv("GOOGLE_CREDENTIALS")
    print(f"Using GOOGLE_CREDENTIALS:  {creds_json_content is not None}",creds_json_content)
    if not creds_json_content:
        print("FATAL ERROR: GOOGLE_CREDENTIALS environment variable not set.")
        return False
        
    tmp_file_name = None

    try:
        # Write the JSON content to a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
            tmp_file.write(creds_json_content)
            tmp_file_name = tmp_file.name

        scope = [
            "https://spreadsheets.google.com/feeds", 
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(tmp_file_name, scope)
        client = gspread.authorize(creds)
        
        # 1. Open the spreadsheet using the ID
        spreadsheet = client.open_by_key(sheet_id)
        sheet = spreadsheet.worksheet(WORKSHEET_NAME) 

        # 2. Get the header row to ensure we match column order
        header = sheet.row_values(1)
        
        # 3. Extract values from the record in the correct order
        # If a key from the header is missing in the incoming JSON, it uses an empty string ''
        row_values = [str(new_record.get(h, '')) for h in header]
        
        # 4. Append the new row to the sheet
        sheet.append_row(row_values)
        
        print(f"SUCCESS: Data successfully appended to Google Sheet ID {sheet_id} in {WORKSHEET_NAME}.")
        return True

    except Exception as e:
        print(f"ERROR writing to Google Sheets: {e}")
        return False
    finally:
        if tmp_file_name and os.path.exists(tmp_file_name):
            os.remove(tmp_file_name)

# --- JSON PAYLOAD CONSTRUCTION ---

def build_whatsapp_payload(record):
    """
    Constructs the complex WhatsApp JSON payload using data received from the POST request.
    
    NOTE: This function assumes the incoming JSON keys match the fields used below.
    """
    
    # Map fields from the incoming request data
    mobile_no = str(record.get('Mobile No', '')).replace(' ', '')
    application_id = str(record.get('Application ID', ''))
    applicant_name = str(record.get('Applicant Name', ''))
    application_type = str(record.get('Application Type (Certificate Name)', ''))

    if not mobile_no or not application_id:
        print("Missing required fields for JSON payload.")
        return None
        
    # Construct the exact nested JSON structure required
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

# --- FLASK API ENDPOINT ---

@app.route('/submit-data', methods=['POST'])
def submit_data():
    """
    Receives JSON data via POST, writes it to Google Sheets, and returns the 
    WhatsApp JSON payload as the API response.
    """
    
    # 1. Get the incoming JSON data from the request body
    incoming_data = request.get_json(silent=True)
    
    if not incoming_data:
        return jsonify({"status": "error", "message": "Invalid JSON received or missing body."}), 400

    if not SHEET_ID:
        return jsonify({"status": "error", "message": "Server configuration missing SHEET_ID."}), 500

    print(f"\n--- Received Data: {incoming_data} ---")
    
    # 2. Write the data to the Google Sheet using the ID
    sheet_success = write_sheet_data(SHEET_ID, incoming_data)
    
    # 3. Construct the WhatsApp JSON payload
    whatsapp_payload = build_whatsapp_payload(incoming_data)
    
    if whatsapp_payload is None:
        return jsonify({"status": "error", "message": "Failed to construct WhatsApp payload (missing mobile/app ID)."}), 400

    # 4. Return the constructed JSON payload to the client
    # The client (Postman/Frontend) will receive this and can then send it to the WhatsApp API.
    
    # Optionally, add sheet status confirmation to the payload for the client
    whatsapp_payload['sheet_write_status'] = "success" if sheet_success else "failure"

    return jsonify(whatsapp_payload), 200

# --- Server Startup (For Local Testing) ---

if __name__ == '__main__':
    # To run this locally, remember to set environment variables first!
    print("\n--- Starting Flask Data Submission API (Listening for POST requests) ---")
    app.run(debug=True, port=5000)