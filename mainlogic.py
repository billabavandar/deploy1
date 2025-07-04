def rename_patient_folder(doc_name, old_patient_name, new_patient_name):
    """
    Renames the patient folder in Google Drive from old_patient_name (usually caseid) to new_patient_name (actual patient name).
    Folder structure: '3d-align' -> doc_name -> old_patient_name -> ...
    """
    drive_service = get_drive()
    if drive_service is None:
        print("Google Drive service not available. Cannot rename folder.")
        return False
    try:
        # Find the parent folder: '3d-align' -> doc_name
        root_folder_id = get_or_create_folder(drive_service, '3d-align', 'root')
        doc_folder_id = get_or_create_folder(drive_service, doc_name, root_folder_id)
        # Find the patient folder by old_patient_name
        query = f"name='{old_patient_name}' and mimeType='application/vnd.google-apps.folder' and '{doc_folder_id}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items:
            print(f"No folder found for patient '{old_patient_name}' under doc '{doc_name}'.")
            return False
        folder_id = items[0]['id']
        # Rename the folder
        file_metadata = {'name': new_patient_name}
        drive_service.files().update(fileId=folder_id, body=file_metadata).execute()
        print(f"Renamed folder from '{old_patient_name}' to '{new_patient_name}' (ID: {folder_id})")
        return True
    except Exception as e:
        print(f"Error renaming patient folder in Google Drive: {e}")
        return False
# ==============================================================================
# 1. IMPORTS
# ==============================================================================
import os
import datetime
import pytz
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
# Third-party libraries
from dotenv import load_dotenv

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError

# LangChain imports
from langchain import hub
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import Tool
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnableBranch, RunnableLambda, RunnableMap
from langchain_openai import ChatOpenAI

# ==============================================================================
# 2. CONFIGURATION AND INITIALIZATION
# ==============================================================================
load_dotenv(override=True)

# --- Configuration Constants ---
CLIENT_SECRET_FILE = 'client_secret.json'
TOKEN_FILE = 'token.json'
CALENDAR_ID = 'cat11july@gmail.com' # Replace with your actual calendar ID
SCOPES = [
    'https://www.googleapis.com/auth/drive',        # For Google Drive access
    'https://www.googleapis.com/auth/calendar'      # For Google Calendar access (if you still need it)
    # Add other Calendar scopes if you use more specific ones, e.g., 'https://www.googleapis.com/auth/calendar.events'
] 

# --- LLM Initialization ---
llm = None
model = None

def get_llm():
    """Initialize LLM if not already initialized."""
    global llm, model
    if llm is None:
        llm = ChatOpenAI(
            model_name="deepseek/deepseek-r1-0528-qwen3-8b:free",
            openai_api_key=os.getenv("OPENROUTER_API_KEY"),
            openai_api_base="https://openrouter.ai/api/v1",
        )
        model = llm
    return llm

# --- Mock Dentist Database ---
# Changed keys to phone numbers
authorized_dentists = {

    # Add more dentists as needed
}

# ==============================================================================
# 3. GOOGLE SERVICE
# ==============================================================================

# Placeholders for Google services
_drive_service = None
_calendar_service = None

def get_drive():
    """Authenticates a user via OAuth 2.0 and returns a Drive service object."""
    global _drive_service
    if _drive_service is not None:
        return _drive_service
    
    creds = None
    
    # The file token.json stores the user's access and refresh tokens.
    # It must be read as text (not binary) because it's JSON.
    if os.path.exists(TOKEN_FILE):
        try:
            # Use Credentials.from_authorized_user_file to load JSON token
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            print(f"Loaded credentials from {TOKEN_FILE}.")
        except Exception as e:
            # Handle cases where token.json might be corrupted or malformed JSON
            print(f"Error loading credentials from {TOKEN_FILE}: {e}. Will re-authenticate.")
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE) # Delete potentially corrupted file
            creds = None

    # If there are no (valid) credentials available or scopes are insufficient, let the user log in.
    # Check if existing creds have all required scopes
    # Use 'in' operator to check if all required scopes are covered, as creds.scopes might contain more
    if not creds or not creds.valid or not all(s in (creds.scopes if creds.scopes else []) for s in SCOPES):
        if creds and creds.expired and creds.refresh_token:
            print("Access token expired or scopes insufficient, attempting to refresh/re-authorize...")
            try:
                creds.refresh(Request())
                # After refresh, re-check if all scopes are covered
                if not all(s in (creds.scopes if creds.scopes else []) for s in SCOPES):
                     raise ValueError("Refreshed token does not cover all required scopes. Initiating full OAuth flow.")
            except (RefreshError, ValueError) as e: # Catch RefreshError and our custom ValueError
                print(f"Refresh failed or scopes insufficient ({e}). Initiating full OAuth 2.0 flow...")
                # If refresh fails or scopes are still not enough, re-authenticate fully
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e: # Catch other potential errors during refresh
                print(f"An unexpected error occurred during refresh: {e}. Initiating full OAuth 2.0 flow...")
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            print("No valid credentials found or scopes insufficient. Initiating full OAuth 2.0 flow...")
            # If no creds or refresh not possible, do full authentication
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run (ALWAYS in JSON format)
        with open(TOKEN_FILE, 'w') as token: # Use 'w' for text mode
            token.write(creds.to_json()) # Write as JSON string
        print(f"Credentials saved to {TOKEN_FILE}")

    try:
        service = build('drive', 'v3', credentials=creds)
        print("Google Drive service initialized successfully.")
        _drive_service = service
        return service
    except HttpError as e:
        print(f"An HTTP error occurred building Drive service: {e}")
        return None
    except Exception as e:
        print(f"Error building Drive service: {e}")
        return None

# The get_calendar_service_oauth function (as you provided) is already correct
# in how it handles token.json (using creds.to_json() and Credentials.from_authorized_user_file).
# So no changes are needed there.

def get_or_create_folder(service, name, parent_id):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    
    # Folder not found, create it
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder['id']

from googleapiclient.http import MediaFileUpload
# Assuming get_drive and get_or_create_folder are defined elsewhere and work correctly

def upload_drive(file_path, file_name, mime_type, doc_name, patient_name, label):
    """
    Uploads a file to Google Drive and returns its direct download link.
    """
    drive_service = get_drive()
    if drive_service is None:
        print("Google Drive service not available. Cannot upload file.")
        return None

    try:
        # Create folder structure: '3d-align' -> doc_name -> patient_name -> 'img'
        root_folder_id = get_or_create_folder(drive_service, '3d-align', 'root')
        doc_folder_id = get_or_create_folder(drive_service, doc_name, root_folder_id)
        patient_folder_id = get_or_create_folder(drive_service, patient_name, doc_folder_id)
        img_folder_id = get_or_create_folder(drive_service, label, patient_folder_id)

        file_metadata = {'name': file_name, 'parents': [img_folder_id]}
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        
        file = drive_service.files().create(body=file_metadata,
                                            media_body=media,
                                            fields='id, webViewLink').execute() # Keep webViewLink for logging/debugging
        file_id = file.get('id')
        web_view_link = file.get('webViewLink') # This is the web view link, not the direct one

        # Make the file publicly accessible (read-only)
        permission = {
            'type': 'anyone',
            'role': 'reader',
            'allowFileDiscovery': False
        }
        drive_service.permissions().create(fileId=file_id, body=permission, fields='id').execute()

        # Construct the direct download link
        direct_download_link = f"https://drive.google.com/uc?export=download&id={file_id}"

        print(f"File uploaded to Google Drive. File ID: {file_id}, Web View Link: {web_view_link}, Direct Download Link: {direct_download_link}")
        folder_metadata = drive_service.files().get(
            fileId=img_folder_id,
            fields='webViewLink'
        ).execute()
        folder_web_view_link = folder_metadata.get('webViewLink')

        # --- Make the folder publicly accessible (read-only) ---
        print(f"Setting public read permission for folder: {img_folder_id}")
        permission = {
            'type': 'anyone',
            'role': 'reader',
            'allowFileDiscovery': False # Optional: Keeps it from appearing in public searches
        }
        drive_service.permissions().create(
            fileId=img_folder_id,
            body=permission,
            fields='id'
        ).execute()
        print("Permission set successfully.")

        print(f"Folder link generated: {folder_web_view_link}")
        # Return the direct download link
        return f"""{web_view_link} -> {folder_web_view_link}"""
        
    except Exception as e:
        print(f"Error uploading file to Google Drive: {e}")
        return None



def get_calendar_service_oauth():
    """
    Initializes and returns the Google Calendar API service using OAuth 2.0 Client ID.
    Handles user authentication via browser for the first run and uses token.json thereafter.
    """
    global _calendar_service
    if _calendar_service is not None:
        return _calendar_service
    
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing existing credentials...")
            try:
                creds.refresh(Request())
            except RefreshError as e:
                print(f"Error refreshing token: {e}. Re-authenticating...")
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            print("No valid token.json found or token expired. Starting new authentication flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        print(f"Authentication successful and token saved to {TOKEN_FILE}.")

    try:
        service = build('calendar', 'v3', credentials=creds)
        print("Google Calendar service initialized successfully.")
        _calendar_service = service
        return service
    except HttpError as error:
        print(f"An HTTP error occurred while building the service: {error}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during service initialization: {e}")
        return None
from langchain.schema import BaseMessage

def ls(memory_obj):
    """
    Converts a LangChain ConversationBufferMemory object to a list of serializable message dicts.
    """
    serializable_messages = []
    for msg in memory_obj.chat_memory.messages:
        # It's good practice to ensure msg is a BaseMessage type before accessing .type and .content
        if hasattr(msg, 'type') and hasattr(msg, 'content'):
            serializable_messages.append({
                "type": msg.type,      # "human", "ai", etc.
                "content": msg.content # Message text
            })
    return serializable_messages

def sl(serializable_messages_list):
    """
    Converts a list of serializable message dicts back into a LangChain ConversationBufferMemory object.
    """
    memory_obj = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    for msg_dict in serializable_messages_list:
        msg_type = msg_dict.get("type")
        msg_content = msg_dict.get("content")
        if msg_type == "human":
            memory_obj.chat_memory.add_message(HumanMessage(content=msg_content))
        elif msg_type == "ai":
            memory_obj.chat_memory.add_message(AIMessage(content=msg_content))
        elif msg_type == "system": # Add if you also store SystemMessages in memory
            memory_obj.chat_memory.add_message(SystemMessage(content=msg_content))
        # Add other message types if you store them (e.g., FunctionMessage)
    return memory_obj

# ==============================================================================
# 4. TOOL DEFINITIONS
# ==============================================================================
def create_tools(calendar_service=None):
    """Creates all the necessary tools for the agents."""
    if calendar_service is None:
        calendar_service = get_calendar_service_oauth()

    # --- Tool Functions ---
    # MODIFICATION: Added 'location' parameter to the function
    def book_calendar_appointment(action_input: str) -> str:
        try:
            # Split the input string into datetime and location
            iso_datetime_str, location = action_input.strip().split(",", 1)
            iso_datetime_str = iso_datetime_str.strip()
            location = location.strip()

            ahmedabad_tz = pytz.timezone('Asia/Kolkata')
            start_time = datetime.datetime.fromisoformat(iso_datetime_str)
            if start_time.tzinfo is None:
                start_time = ahmedabad_tz.localize(start_time)

            end_time = start_time + datetime.timedelta(minutes=30)

            # Convert raw lat,long to Google Maps URL if necessary
            if "," in location and "http" not in location:
                lat_lon = location.replace(" ", "")
                location_url = f"https://maps.google.com/?q={lat_lon}"
                location_for_calendar = location_url
                location_description = f"Patient scanning session for 3D-Align aligners at coordinates {lat_lon}.\nMap: {location_url}"
            else:
                location_for_calendar = location
                location_description = f"Patient scanning session for 3D-Align aligners at {location}."

            event = {
                'summary': '3D-Align Scanning Appointment',
                'location': location_for_calendar,
                'description': location_description,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': str(ahmedabad_tz),
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': str(ahmedabad_tz),
                },
            }

            created_event = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            print(f"Event created: {created_event.get('htmlLink')}")
            return f"✅ Success! The appointment has been booked for {start_time.strftime('%A, %B %d at %I:%M %p')} at {location_for_calendar}."

        except ValueError:
            return "❌ Invalid input format. Please provide in format: ISO_DATETIME,LOCATION"
        except HttpError as e:
            return f"❌ Failed to book appointment due to a Google API error: {e}"
        except Exception as e:
            return f"❌ An unexpected error occurred while booking the appointment: {e}"

    def check_calendar_availability(iso_datetime_str: str) -> str:
        """
        Check if a given time in ISO 8601 format (e.g., 2025-06-11T15:30) is free.
        """
        try:
            dt_object = datetime.datetime.fromisoformat(iso_datetime_str)
            ahmedabad_tz = pytz.timezone('Asia/Kolkata')
            if dt_object.tzinfo is None:
                localized_dt = ahmedabad_tz.localize(dt_object)
                start_time_utc = localized_dt.astimezone(pytz.utc)
            else:
                start_time_utc = dt_object.astimezone(pytz.utc)

            end_time_utc = start_time_utc + datetime.timedelta(minutes=30)
            events_result = calendar_service.events().list(
                calendarId=CALENDAR_ID, timeMin=start_time_utc.isoformat(),
                timeMax=end_time_utc.isoformat(), singleEvents=True, orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            if not events:
                return f"The slot at {iso_datetime_str} is available on {CALENDAR_ID}."
            else:
                summary = events[0].get('summary', 'an unknown event')
                return f"The slot at {iso_datetime_str} is NOT available on {CALENDAR_ID} due to an event: '{summary}'."
        except ValueError as e:
            return f"Invalid datetime format. Please use ISO 8601 (e.g., 2025-06-11T15:30). Error: {e}"
        except HttpError as e:
            return f"Failed to check calendar due to a Google API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred during calendar check: {e}"


   

    # --- Tool Instantiation ---

    scheduling_tools = [
        Tool(
            name="CheckCalendarAvailability",
            func=check_calendar_availability,
            description="Check if a given time in ISO format (e.g. 2025-06-11T15:30) is free on the client's calendar."
        ),
        Tool(
            name="BookCalendarAppointment",
            func=book_calendar_appointment,
            # MODIFICATION: Updated description to include location
            description="Use this final tool to book the appointment on the calendar. This should only be used when the user explicitly confirms an available timeslot AND you have collected their clinic location. The input MUST include both the 'iso_datetime_str' for the confirmed slot (e.g., '2025-06-13T15:00:00') and the 'location' string (e.g., 'Smile Dental Studio, Ahmedabad')."
        )
    ]

    return scheduling_tools


# ==============================================================================
# 5. MAIN EXECUTION LOGIC (for local testing)
# ==============================================================================
if __name__ == "__main__":
   service = get_calendar_service_oauth()
   service = get_drive()