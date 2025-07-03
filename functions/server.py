# ==============================================================================
# 1. IMPORTS
# ==============================================================================
import os
import requests
from flask import Flask, request, send_from_directory
from werkzeug.utils import safe_join # Import safe_join from its new location
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from dotenv import load_dotenv
import mimetypes
import tempfile
import uuid # For unique file names in temp directory to avoid clashes
import threading # For cleaning up files after a delay
import uuid
import os
import firebase_admin
from firebase_admin import db # Import the Realtime Database service
from firebase_admin import credentials # Generally not needed if using ADC, but good to know
import sys
import time
from datetime import datetime
import re
import subprocess
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from typing import Any, List, Optional
import re
from pydantic import Field

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult
from langchain_core.messages import BaseMessage
from typing import List
import re
# Removed import prod_workflow (not needed for WhatsApp messaging)
from flask import Flask, request
import requests
import json
import time

# 🔐 Meta Credentials (replace with your actual credentials)
# ------------------------------------------------------------------
VERIFY_TOKEN = "12345"

PHONE_NUMBER_ID = "719531424575718"
class NoThinkLLMWrapper(BaseChatModel):
    wrapped_llm: BaseChatModel

    @property
    def _llm_type(self) -> str:
        return "no_think_llm"

    def _strip_think_tags(self, text: str) -> str:
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    def _generate(
        self, messages: List[BaseMessage], stop=None, run_manager=None, **kwargs
    ) -> ChatResult:
        result = self.wrapped_llm._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        for gen in result.generations:
            gen.message.content = self._strip_think_tags(gen.message.content)
        return result


FIREBASE_DATABASE_URL = "https://diesel-ellipse-463111-a5-default-rtdb.asia-southeast1.firebasedatabase.app/"

# Placeholder for Firebase app and database reference
firebase_app = None
root_ref = None

def get_firebase_app():
    """Initialize Firebase app if not already initialized."""
    global firebase_app
    if firebase_app is None:
        try:
            firebase_app = firebase_admin.initialize_app(
                options={'databaseURL': FIREBASE_DATABASE_URL}
            )
            print(f"Firebase app initialized successfully for Realtime Database: '{FIREBASE_DATABASE_URL}'.")
        except Exception as e:
            print(f"ERROR: Could not initialize Firebase Admin SDK or connect to Realtime Database.")
            print(f"Please ensure you have replaced 'YOUR_REALTIME_DATABASE_URL_HERE' with your actual URL,")
            print(f"and that ADC are configured and billing is enabled for your project.")
            print(f"Error details: {e}")
            raise e
    return firebase_app

def get_db_ref():
    """Get database reference, initializing Firebase if needed."""
    global root_ref
    if root_ref is None:
        get_firebase_app()  # Ensure Firebase is initialized
        root_ref = db.reference('/')
    return root_ref

bot_response =""
# Import the necessary functions and components from your mainlogic.py
from mainlogic import (
    get_calendar_service_oauth,
    create_tools,
    ChatOpenAI,
    hub,
    Tool,
    create_structured_chat_agent,
    AgentExecutor,
    ConversationBufferMemory,
    SystemMessage,
    HumanMessage,
    AIMessage,
    StrOutputParser,
    ChatPromptTemplate,
    RunnableBranch,
    RunnableLambda,
    RunnableMap,
    ls,
    sl,
    get_drive,
    upload_drive
)
output_parser = StrOutputParser()
# ==============================================================================
# 2. CONFIGURATION AND INITIALIZATION
# ==============================================================================
load_dotenv(override=True) # This line should be at the very top of your configuration section

app = Flask(__name__)


# Add these lines temporarily for debugging
print(f"Loaded TWILIO_ACCOUNT_SID: {os.getenv('TWILIO_ACCOUNT_SID')}")
print(f"Loaded TWILIO_AUTH_TOKEN: {os.getenv('TWILIO_AUTH_TOKEN')}")
print(f"Loaded NGROK_URL: {os.getenv('NGROK_URL')}")
# ... rest of your code ...
# --- Twilio Configuration ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
FORWARD_TO_WHATSAPP_NUMBER = os.getenv("FORWARD_TO_WHATSAPP_NUMBER")
ACCESS_TOKEN = os.getenv("ACESS")
print(TWILIO_WHATSAPP_NUMBER)
print(FORWARD_TO_WHATSAPP_NUMBER)

# Placeholder for Twilio client
twilio_client = None

def get_twilio_client():
    """Initialize Twilio client if not already initialized."""
    global twilio_client
    if twilio_client is None:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return twilio_client

# --- Temporary storage for media files ---
# --- Temporary storage for media files ---
MEDIA_TEMP_DIR = os.path.join(tempfile.gettempdir(), "twilio_media_bot")
os.makedirs(MEDIA_TEMP_DIR, exist_ok=True)
print(f"Temporary media directory: {MEDIA_TEMP_DIR}")

# Placeholder for Firebase user sessions reference
user_sessions_fb = None

def get_user_sessions_fb():
    """Get user sessions Firebase reference, initializing if needed."""
    global user_sessions_fb
    if user_sessions_fb is None:
        root_ref = get_db_ref()
        user_sessions_fb = root_ref.child('user_sessions')
    return user_sessions_fb

# Placeholder for LLM
llm = None
model = None

def get_llm():
    """Initialize LLM if not already initialized."""
    global llm, model
    if llm is None:
        llm = ChatOpenAI(
            model_name="deepseek/deepseek-r1-0528:free",
            openai_api_key=os.getenv("OPENROUTER_API_KEY"),
            openai_api_base="https://openrouter.ai/api/v1",
        )
        
        #llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
        llm = ChatOllama(model="deepseek-r1:7b")
        llm = NoThinkLLMWrapper(wrapped_llm=llm)
        llm = ChatOllama(model="llama3.1", temperature=0.6)
        model = llm
    return llm
#======================================
#intent prompts
intent_classification_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an helpful assistant"),
            ("human", """You are an AI assistant for 3D Align, and your job is to classify the intent of the user's message into one of the following four categories:

1. New Aligner Case Inquiry - for dentists or users who want to submit, inquire or require quotation about a **new aligner case** .
2. Existing Aligner Case Trouble-Shoot - for issues, complaints, or help needed for an **ongoing or completed aligner case**.
3. Aligner By-Products - for questions about **products related to aligner use**, such as chewies, aligner cases, cleaning kits, etc.
4. Finances Related Query - for queries involving **payments, invoices, pricing, or refunds**.

Respond with only the **exact name** of the category that best matches the user's message. If the message is unclear or does not match any, respond with: `Unclear Intent`.

---

User Message: {input}

---

Intent:""")
        ])
express_prompt = ChatPromptTemplate.from_template(
    """You are a helpful assistant that classifies doctor responses into three categories based on urgency.

Categories:
- "express" - if the doctor clearly indicates urgency or requests faster processing.
- "normal" - if the doctor accepts standard processing time or shows no urgency.
- "unrelated" - if the response is not related to urgency or turnaround time at all.

Classify the following doctor response into one of these categories.

Response: "{input}"

Classification (express/normal/unrelated):"""
)

confirm_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an AI assistant that analyzes user responses."),
    ("human", """You are given a yes-or-no question and a user's response.

Task:
- Determine if the user's response indicates **Yes** or **No**.
- If the response is unclear or ambiguous, return `Unknown`.
- Respond with **only one word**: Yes, No, or Unknown.

Question: {question}
User's Response: {input}
""")
])

new_aligner_case_prompt = ChatPromptTemplate.from_messages([
    ("human","""You are an intent classifier for a dental aligner assistant chatbot.  
Your job is to classify the user's response into one of the following intents:

1. **submit_case** - if the user wants to directly submit the aligner case.
2. **request_quotation** - if the user wants a quotation before proceeding.
3. **other** - if the user's message does not match either of the above intents.

Classify the intent based on the user's message.  
Respond with only the intent label (`submit_case`, `request_quotation`, or `other`) and nothing else.

Examples:
- "I want to go ahead and submit the case." → `submit_case`
- "Can I get a quotation first?" → `request_quotation`
- "Can you help me with something else?" → `other`

Now classify this message:
{user_input}""")])

choose_prompt = ChatPromptTemplate.from_template("""
You are a helpful assistant for a dental aligner service. Classify the user's message into one of the following categories:

1. "submit_scan" - if the user already has an intraoral scan or PVS impression and wants to send or submit it through whatsapp or email.
2. "schedule_scan" - if the user wants to schedule an intraoral scan or is asking about booking one.
3. "unrelated" - if the message does not clearly match either of the above.

User message: "{input}"

Respond with only one of these three labels: submit_scan, schedule_scan, or unrelated.
""")

byproduct_prompt = ChatPromptTemplate.from_template("""
You are an intelligent product assistant. A user may ask about a dental product listed in the following catalog:

Products:
- Pediatric Retainer
- Twin Block
- Guided Essix Retainer
- Essix Retainer
- Bruxism Splint
- TMJ Splint
- Bleaching Trays

Your task is to:
- If the user is requesting *more information* or *details* about any product in the list, return **only the exact product name** (e.g., "Bruxism Splint").
- If the user is trying to *place an order* (e.g., "order now", "I want to buy", "please send me"), return **"order"**.
- If the input doesn't match any of the products or an ordering intent, return **"none"**.

Here is the user message:
{user_input}
""")

# Placeholder for intent chains
intent_chain = None
confirm_chain = None
new_aligner_case_chain = None
express_chain = None
choose_chain = None
byproduct_chain = None

def get_intent_chains():
    """Initialize intent chains if not already initialized."""
    global intent_chain, confirm_chain, new_aligner_case_chain, express_chain, choose_chain, byproduct_chain
    if intent_chain is None:
        llm = get_llm()
        intent_chain = intent_classification_prompt | llm | output_parser
        confirm_chain = confirm_prompt | llm | output_parser
        new_aligner_case_chain = new_aligner_case_prompt | llm | output_parser
        express_chain = express_prompt | llm | output_parser
        choose_chain = choose_prompt | llm | StrOutputParser()
        byproduct_chain = byproduct_prompt | llm | output_parser
    return intent_chain, confirm_chain, new_aligner_case_chain, express_chain, choose_chain, byproduct_chain
# --- Global state for each user (for simplicity; ideally use a database) ---

# ==============================================================================
# 3. HELPER FUNCTIONS FOR BOT LOGIC INTEGRATION
# ==============================================================================
def start_localtunnel():
    try:
        # Path to the lt.cmd installed via npm (adjust if different)
        lt_cmd = os.path.expanduser("~\\AppData\\Roaming\\npm\\lt.cmd")

        subprocess.Popen(
            [lt_cmd, '--port', '5000', '--subdomain', 'felesai'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True
        )
        print("LocalTunnel started on https://felesai.loca.lt")
    except Exception as e:
        print(f"Error starting LocalTunnel: {e}")
def byprod(cleaned_text,link):
    cleaned_text = cleaned_text.replace("\n", " ").replace("\t", " ").strip()

        # Send WhatsApp template
    return {
                "name": "eachprod",
                "variables": [
                    {"type": "text", "text": cleaned_text}
                ],
                "variables_head": [
                    {
                        "type": "image",
                        "image": {
                            "link": "https://i.ibb.co/ZpcvMQfS/Screenshot-2024-09-03-212649.png"
                        }
                    }
                ]
            }

def delete_file_after_delay(file_path, delay=60):
    """Deletes a file after a specified delay in a separate thread."""
    def _delete_file():
        try:
            # Give Twilio some time to fetch the media
            threading.Event().wait(delay)
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Successfully deleted temporary file: {file_path}")
        except Exception as e:
            print(f"Error deleting temporary file {file_path}: {e}")

    # Start the deletion in a new thread
    thread = threading.Thread(target=_delete_file)
    thread.daemon = True # Allow the program to exit even if thread is running
    thread.start()
def send_message_to_user(user_id, case_id, case_data):
    """Sends the quotation details to the original user."""
    quote_text = case_data.get('quotation_text', "Your quotation is ready!")
    quote_media = case_data.get('quotation_media_links', [])

    message_body = f"Hello! The quotation for your case (ID: {case_id}) is ready.\n\n{quote_text}\n\nDo you want to proceed with this quotation?"
    
    try:
        # Send text message
        get_twilio_client().messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=user_id,
            body=message_body
        )
        print(f"Sent quotation text to {user_id} for case {case_id}.")

        # Send media messages if any
        for media_link in quote_media:
            get_twilio_client().messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=user_id,
                media_url=[media_link]
            )
            print(f"Sent quotation media to {user_id} for case {case_id}.")

    except Exception as e:
        print(f"ERROR sending quotation to user {user_id}: {e}")
    """Sends the quotation details to the original user."""
    quote_text = case_data.get('quotation_text', "Your quotation is ready!")
    quote_media = case_data.get('quotation_media_links', [])

    message_body = f"Hello! The quotation for your case (ID: {case_id}) is ready.\n\n{quote_text}\n\nDo you want to proceed with this quotation?"
    
    try:
        # Send text message
        get_twilio_client().messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=user_id,
            body=message_body
        )
        print(f"Sent quotation text to {user_id} for case {case_id}.")

        # Send media messages if any
        for media_link in quote_media:
            get_twilio_client().messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=user_id,
                media_url=[media_link]
            )
            print(f"Sent quotation media to {user_id} for case {case_id}.")

    except Exception as e:
        print(f"ERROR sending quotation to user {user_id}: {e}")
def register_dentist(details: str) -> str:
        """Registers a new dentist and updates state.
        Input format: Name, Phone Number, Clinic, License Number.
        """
        try:
            name, phone_number, clinic, license_number = [x.strip() for x in details.split(",")]
            
            cleaned_phone_number = phone_number.replace("whatsapp:", "").strip()
            if not cleaned_phone_number.startswith('+'):
                print(f"Warning: Phone number '{phone_number}' does not start with '+'. Attempting to prepend '+'.")
                cleaned_phone_number = '+' + cleaned_phone_number
            user_sessions_fb.child("whatsapp:"+str(phone_number)).update({
                "name": name,
                "clinic": clinic,
                "license": license_number
            })

            return f"{name} has been successfully registered you should simply greet them now."
        except Exception as e:
            return f"Invalid format. Please use: Name, Phone Number, Clinic, License Number. Error: {e}"

def update_db(user_id,session) :
    user_sessions_fb.child(user_id).update(session)

def initialize_user_session(user_id):
    """Initializes the session state for a new user."""
    user_sessions_fb = get_user_sessions_fb()
    user_sessions_fb.child(user_id).set({
            'app_state': "",
            'auth_memory' : False,
            'sched_memory' : False,
            'calendar_service': True,
            'current_stage': 'auth',
            'last_question': "",
            'image_count': 0,
        })

def forward_media_to_number(media_url, sender_whatsapp_id, label="images"):
    """
    Downloads media from WhatsApp Cloud API URL, saves it locally,
    uploads it to Google Drive, and sends a text message with the Drive link.
    """
    temp_file_name = None
    try:
        if not FORWARD_TO_WHATSAPP_NUMBER:
            print("FORWARD_TO_WHATSAPP_NUMBER is not set in .env. Cannot forward media.")
            return False

        print(f"Attempting to download media from: {media_url}")

        # Download media with Cloud API auth
        response = requests.get(media_url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
        response.raise_for_status()

        # Get file extension from content-type header
        content_type = response.headers.get('Content-Type')
        extension = mimetypes.guess_extension(content_type) if content_type else '.bin'
        if not extension and '.' in media_url:
            extension = os.path.splitext(media_url)[1]
        if not extension:
            extension = '.jpeg'

        # Generate unique filename
        temp_file_name = f"{uuid.uuid4()}{extension}"
        temp_file_path = os.path.join(MEDIA_TEMP_DIR, temp_file_name)

        with open(temp_file_path, 'wb') as temp_media_file:
            temp_media_file.write(response.content)

        print(f"Media downloaded to temporary file: {temp_file_path}")
        print(sender_whatsapp_id)

        client_fb = user_sessions_fb.child(sender_whatsapp_id)
        caseid = client_fb.child('active').get()

        # Upload to Google Drive
        drive_link = upload_drive(
            temp_file_path,
            temp_file_name,
            content_type,
            client_fb.child('name').get(),
            client_fb.child(caseid).child('name').get(),
            label
        )

        if not drive_link:
            print("Failed to upload file to Google Drive. Cannot send link.")
            return False

        print(f"Uploaded to Google Drive. Link: {drive_link}")

        # Send text message with drive link
        # Corrected function call 
        if label == "images" :
            id = send_whatsapp_template("917801833884", {
        "name": "final_quote",
        "variables": [
            {"type": "text", "text": client_fb.child('name').get()+"  "+ sender_whatsapp_id}, # Corresponds to {{1}}
            {"type": "text", "text": "caseid: "+caseid},                         # Corresponds to {{2}}
            {"type": "text", "text": drive_link}                      # Corresponds to {{3}}
        ]
    })
            get_db_ref().child("quote").child(id.replace("=", "").replace(".", "-")).set({"client" : sender_whatsapp_id,"caseid" : caseid})
            delete_file_after_delay(temp_file_path, delay=5)
            return True
        else :
            send_whatsapp_text("917801833884",f"Recieved .stl Files from Dr. {client_fb.child('name').get()} -> {sender_whatsapp_id} for caseid: {caseid} link-> {drive_link}")
            delete_file_after_delay(temp_file_path, delay=5)
            return True

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"Error in media forwarding: {e}")
    finally:
        if temp_file_name:
            temp_file_path = os.path.join(MEDIA_TEMP_DIR, temp_file_name)
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    return False

def handle_production(msgid,msg) :
    data = get_db_ref().child("quote").child(msgid.replace("=", "").replace(".", "-")).get()
    print(data)
    user_sessions_fb = get_user_sessions_fb()
    user_sessions_fb.child(data["client"]).child(data["caseid"]).child("quote").set(msg)
    # Fetch patient name from namebook, fallback to 'current patient' if not found
    patient_name = get_db_ref().child('namebook').child(data['caseid']).get() or data['caseid']
    send_whatsapp_text(data["client"], f"Your quotation for {patient_name} has been processed successfully. It is {msg} ")
    user_sessions_fb.child(data["client"]).child("active").set(data["caseid"])
    user_sessions_fb.child(data["client"]).child("current_stage").set("awaiting_quote")
    user_sessions_fb.child(data["client"]).child("image_count").set(0)

    


def handle_bot_logic(user_id, message_body, num_media, media_urls, media_content_types,session):
    manual_test =False
    temp = False
    caseid =""
    
    # Initialize lazy loaded components
    get_llm()  # Ensure LLM is loaded
    intent_chain, confirm_chain, new_aligner_case_chain, express_chain, choose_chain, byproduct_chain = get_intent_chains()
    user_sessions_fb = get_user_sessions_fb()
    
     # --- Memory Deserialization at the START ---
    # Ensure 'auth_memory' is a ConversationBufferMemory object
    if 'auth_memory' in session and session['auth_memory'] is not False and session['auth_memory'] is not None:
        if isinstance(session['auth_memory'], list):
            try:
                session['auth_memory'] = sl(session['auth_memory'])
                print("Auth memory deserialized from session (list -> object).")
            except Exception as e:
                print(f"Error deserializing auth_memory: {e}. Reinitializing.")
                session['auth_memory'] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        # If it's already an object, do nothing (e.g., from prior logic in the same request)
    else:
        # Initialize if not present or was explicitly False/None
        session['auth_memory'] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        print("Auth memory initialized anew.")

    # Ensure 'sched_memory' in session and that it's serializable
    if 'sched_memory' in session and session['sched_memory'] is not False and session['sched_memory'] is not None:
        if isinstance(session['sched_memory'], list):
            try:
                session['sched_memory'] = sl(session['sched_memory'])
                print("Sched memory deserialized from session (list -> object).")
            except Exception as e:
                print(f"Error deserializing sched_memory: {e}. Reinitializing.")
                session['sched_memory'] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        # If it's already an object, do nothing
    else:
        # Initialize if not present or was explicitly False/None
        session['sched_memory'] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        print("Sched memory initialized anew.")
    
    """
    Integrates the bot's logic from mainlogic.py to process a single message.
    """
    global output_parser

    # ... (Code for 'auth', 'intent', 'awaiting_images' stages remains the same) ...
    # --- DEBUGGING PRINTS ---
    print(f"\n--- handle_bot_logic for User: {user_id} ---")
    print(f"Incoming message: '{message_body}'")
    print(f"Current stage: {session['current_stage']}")
    print(f"Num media: {num_media}, Media URLs: {media_urls}")
    print(f"App state before processing: {session['app_state']}")

    bot_response = "I'm sorry, I couldn't process your request." # Default response

    if not session['calendar_service']:
        print("Calendar service not initialized.")
        return "Sorry, I'm unable to connect to the calendar service at the moment. Please try again later."
    auth_tools = [
        Tool(
            name="DentistRegistrar",
            func=register_dentist,
            description="Register a new dentist. Input format: Name, Phone Number, Clinic, License Number. confirms you have collected all required fields."
        )
    ]
    scheduling_tools = create_tools()
    output_parser = StrOutputParser()

    # --- Authorization Stage ---
    if session['current_stage'] == 'auth':
        print("Processing in 'auth' stage...")
        pure_sender_phone = user_id.replace("whatsapp:", "").strip()
        registration_prompt = hub.pull("hwchase17/structured-chat-agent") + """
You are a structured AI assistant responsible for registering dentists to 3D-Align.

---

## 🚨 Response Format:

You must always respond using a **structured JSON object**, like this:

{{
  "action": "ActionName",
  "action_input": "your string here"
}}

- Do **not** include any text outside of this JSON.
- Do **not** use Markdown or code formatting in the output.
- Never return anything except this JSON object.

---

## 🎯 Goal: Register a dentist to 3D-Align

---

### Step 1 - Start the Conversation

Start by greeting the user politely and offering to help with registration:

{{
  "action": "Final Answer",
  "action_input": "Hi there! Welcome to 3D-Align. I'd be happy to help you register. May I please have your full name?"
}}

---

### Step 2 - Collect Required Details

You must collect **all three** of the following:

1. Full Name  
2. Clinic Name  
3. Dental License Number

Ask one at a time. For example:

- If full name is missing:
{{
  "action": "Final Answer",
  "action_input": "Could you please share your full name?"
}}

- If clinic name is missing:
{{
  "action": "Final Answer",
  "action_input": "Thanks! What's the name of your clinic?"
}}

- If license number is missing:
{{
  "action": "Final Answer",
  "action_input": "Lastly, may I have your dental license number?"
}}

Only ask for details that haven't been provided yet. Always review chat history to avoid repetition.

---

### Step 3 - Register Dentist

Once you have all details, call the tool like this only if registration is still pending:

{{
  "action": "DentistRegistrar",
  "action_input": "<full_name>,<clinic_name>,<license_number>"
}}

---

### Step 4 - Confirm Registration

If registration is successful:

{{
  "action": "Final Answer",
  "action_input": "Registration successful. Welcome to 3D-Align. How can I assist you today?"
}}

---

## 🧠 Rules Recap

- ❌ Never return plain text outside JSON
- ❌ Never show examples to the user
- ✅ Always wait for full name, clinic, and license before registering
- ✅ Be polite and brief in all responses
"""

            # Create agent and executor for registration only
        auth_agent = create_structured_chat_agent(llm=llm, tools=auth_tools, prompt=registration_prompt)
        auth_executor = AgentExecutor.from_agent_and_tools(
                agent=auth_agent, tools=auth_tools, verbose=True, memory=session['auth_memory'], handle_parsing_errors=True
            )
            # Prepare input message
        input_to_agent = message_body
        if not session['auth_memory'].chat_memory.messages or (
                len(session['auth_memory'].chat_memory.messages) == 1 and isinstance(session['auth_memory'].chat_memory.messages[0], SystemMessage)
            ):
            input_to_agent = f"User's phone number: {pure_sender_phone}. User says: {message_body}"
            print(f"First registration input crafted: {input_to_agent}")
            session['auth_memory'].chat_memory.add_message(HumanMessage(content=input_to_agent))

        try:
            response = auth_executor.invoke({"input": input_to_agent})
            bot_response = response["output"]
            print(f"Registration agent response: {bot_response}")

            if "Registration successful" in bot_response:
                session['current_stage'] = 'intent'
                session['auth_memory'].clear()

        except Exception as e:
            print(f"Error during registration agent execution: {e}")
            return "An error occurred during registration. Please try again."

    # --- Intent Detection Stage ---
    elif session['current_stage'] == 'intent':
        print("Processing in 'intent' stage...")  
        try:
            session['app_state'] = intent_chain.invoke({"input": message_body})
            print(session['app_state'])
        except Exception as e:
            print(f"Error during intent chain invocation: {e}")
            return "An error occurred while determining your intent. Please try again."


        if 'New Aligner Case Inquiry' in session['app_state']:
            session['current_stage'] = 'new_aligner'
            temp = {"name" : "proceed1"}
            bot_response = """Thank you for choosing 3D-Align for your aligner case.
Please choose how you'd like to proceed with the new aligner case:
"""         
        elif 'Existing Aligner Case Inquiry' in session['app_state']:
            session['current_stage'] = 'existing_aligner'
            bot_response = """Thank you for reaching out to 3D-Align regarding your existing aligner case. Please provide the patient name or case ID to proceed with your inquiry."""
            session['current_stage'] = 'case_tracking'
        elif 'Unclear Intent' in session['app_state']:
            temp ={"name" : "greeting1"}
            bot_response = "Welcome to 3D-Align How may I help you ?"
        elif 'Aligner By-Products' in session['app_state']:
            session['app_state'] = False
            temp = {"name" : "byproduct","variables_head" : [
    {
      "type": "document",
      "document": {
        "link": "https://drive.google.com/uc?export=download&id=1MmhtCKPQtasPkVOGYJrywt4VXvP7rkDB",
        "filename": "catalog.pdf"
      }
    }
  ]}

            session["current_stage"] = "choose_by"
    elif session["current_stage"] == "choose_by":
        message_body = byproduct_chain.invoke({"user_input" : message_body})
        message_body = message_body.strip().lower()
        bot_response = ""
        image_link = ""
        if "order" in message_body:
            if session['app_state']:
                caseid = str(uuid.uuid4())
                session[caseid] ={}
                session['active'] = caseid
                session[caseid]['quote'] = get_db_ref().child("products").child(session["app_state"]).get("price",0) 
                session[caseid]['name'] = caseid
                session['current_stage'] = "fetching_name"
                bot_response = "Great please let us know the full name of patient"
            else:
                bot_response = "Please select or tell me the product you want to order"
        elif "pediatric retainer" in message_body:
            bot_response = (
                "🦷 *Pediatric Retainer*\n"
                "Prevents space loss due to premature exfoliation of milk teeth and guides eruption of permanent teeth.\n"
                "Also preserves aesthetics of the patient.\n"
                "💰 *Price:* ₹750/-"
            )
            image_link = "https://yourdomain.com/images/pediatric_retainer.jpg"
            session["app_state"] = "pediatric retainer"
            temp = byprod(bot_response,image_link)

        elif "twin block" in message_body:
            bot_response = (
                "🦷 *Twin Block Appliance*\n"
                "Bite blocks with occlusal inclined planes for jaw correction. Separate upper and lower units, worn 24/7 (remove while eating).\n"
                "💰 *Price:* ₹4,000/-"
            )
            image_link = "https://yourdomain.com/images/twin_block.jpg"
            session["app_state"] = "twin block"
            temp = byprod(bot_response,image_link)

        elif "guided essix retainer" in message_body:
            bot_response = (
                "🦷 *Guided Essix Retainer*\n"
                "Clear transparent tray with artificial teeth to preserve appearance during teeth replacement. Avoid chewing/drinking to prevent stains.\n"
                "💰 *Price:* ₹750/-"
            )
            image_link = "https://yourdomain.com/images/guided_essix_retainer.jpg"
            session["app_state"] = "guided essix retainer"
            temp = byprod(bot_response,image_link)

        elif "essix retainer 1.0mm" in message_body:
            bot_response = (
                "🦷 *Essix Retainer – 1.0mm*\n"
                "Clear transparent tray to retain teeth alignment results from braces or aligners.\n"
                "💰 *Price:* ₹500/-"
            )
            image_link = "https://yourdomain.com/images/essix_retainer_1mm.jpg"
            session["app_state"] = "essix retainer 1.0mm"
            temp = byprod(bot_response,image_link)

        elif "essix retainer 0.8mm" in message_body:
            bot_response = (
                "🦷 *Essix Retainer – 0.8mm*\n"
                "Clear transparent tray to retain teeth alignment results from braces or aligners.\n"
                "💰 *Price:* ₹1,000/-"
            )
            image_link = "https://yourdomain.com/images/essix_retainer_0.8mm.jpg"
            session["app_state"] = "essix retainer 0.8mm"
            temp = byprod(bot_response,image_link)

        elif "bruxism splint" in message_body:
            bot_response = (
                "🦷 *Bruxism Splint*\n"
                "Protects teeth from wear due to grinding/clenching. Helps relieve jaw muscle tension and pain.\n"
                "🧾 Available Sizes: 0.5mm | 1.0mm | 1.5mm\n"
                "💰 *Price:* ₹700/-"
            )
            image_link = "https://yourdomain.com/images/bruxism_splint.jpg"
            session["app_state"] = "bruxism splint"
            temp = byprod(bot_response,image_link)

        elif "tmj splint" in message_body:
            bot_response = (
                "🦷 *TMJ Splint*\n"
                "Improves jaw function and reduces pain by modifying occlusal bite and jaw positions.\n"
                "🧾 Available Sizes: 1.5mm | 2.0mm\n"
                "💰 *Price:* ₹2,000/-"
            )
            image_link = "https://yourdomain.com/images/tmj_splint.jpg"
            session["app_state"] = "tmj splint"
            temp = byprod(bot_response,image_link)
        elif "bleaching trays" in message_body:
            bot_response = (
                "🦷 *Bleaching Trays*\n"
                "Clear trays (0.6mm - 1.0mm) for holding whitening gel to bleach teeth surfaces.\n"
                "🧾 Available Sizes: 0.6mm | 1.0mm\n"
                "💰 *Price:* ₹700/-"
            )
            image_link = "https://yourdomain.com/images/bleaching_trays.jpg"
            session["app_state"] = "bleaching trays"
            temp = byprod(bot_response,image_link)
           
        
        else:
            bot_response = (
                "❓ Sorry, I couldn't find that product. Please select the product name as shown in the catalog."
            )

        
    elif session['current_stage'] == 'new_aligner' :
        session['app_state'] = new_aligner_case_chain.invoke({"user_input" : message_body})
        if 'request_quotation' in session['app_state'] :
            session['current_stage'] = "awaiting_images"
            caseid = str(uuid.uuid4())
            session[caseid] ={}
            session['active'] = caseid
            session[caseid]['quote'] = "..." 
            session[caseid]['name'] = caseid
            bot_response = """Requisite for Aligner Case Submission to 3D Align 

1. Intraoral & Extraoral Photographs 
    (Based on this we will be able to roughly give you idea regarding range of aligners required   
    for your case so that you can have rough estimate to quote to your patient before 
    proceeding for next step) 
2. Intraoral Scan / PVS Impression 
3. OPG (Mandatory) 
4. Lateral Cephalohram / CBCT (if required our 3D Align Team will contact you for the same) 

Note :- 
Prior to Intraoral Scanning / Impression taking we recommend you to execute and confirm with our 3D Align Team : 
Scaling & Polishing 
Restorations
Prosthetic Replacements
Disimpaction / Teeth Removal
Interproximal Reduction (as directed by our 3D Align team) 

This recommendation criteria is enforced in order to have better aligner fit and to avoid any discrepancies during ongoing aligner treatment which might affect the results. If not executed as directed by 3D Align team than treating dentist would be responsible for the same. 
To Proceed Further share the Images
"""
        elif 'submit_case' in session['app_state'] :
            session['current_stage'] = "fetching_name"
            caseid = str(uuid.uuid4())
            session[caseid] ={}
            session['active'] = caseid
            session[caseid]['quote'] = "..." 
            session[caseid]['name'] = caseid
            bot_response = "great Please let us know the name of patient"
            session['app_state'] = "direct"
        elif 'other' in session['app_state'] :
            temp = {"name" : "proceed1"}
            bot_response = "Please choose one of the following options or you would like to do something else ?"
            
    elif session['current_stage'] == 'awaiting_images':
        print("Processing in 'awaiting_images' stage...")
        if num_media > 0:
            print(f"Received {num_media} media items. Attempting to forward...")
            successful_forwards = 0
            for url in media_urls:
                if forward_media_to_number(url, user_id):
                    successful_forwards += 1
                else:
                    print(f"Failed to forward media: {url}")
            session['image_count'] += successful_forwards
            if successful_forwards > 0:
                bot_response = f"I have sucessfully recieved {session['image_count']} image(s). type 'DONE' to proceed further"
            else:
                bot_response = "There was an error forwarding your images. Please try again or type 'DONE' if you have nothing to send."
            print(f"Bot response in 'awaiting_images' after media: {bot_response}")

        elif message_body.lower() == 'done':
            print("User typed 'DONE' in 'awaiting_images' stage.")
            if session['image_count'] > 0 or manual_test:
                bot_response = f"Thank you for submitting { session['image_count'] } image(s). We will review them and get back to you with a quotation shortly"
                session['current_stage'] = 'awaiting_quote'
                session['image_count'] = 0 # Reset image count 
                print(f"Transitioned to 'scheduling_quote_confirm'. Bot response: {bot_response}")
            else:
                bot_response = "You haven't sent any images yet. Please send images to proceed further"
        else:
             bot_response = f"You have sent {session['image_count']} images. type 'DONE' to proceed further"

    elif session['current_stage'] == 'awaiting_quote':
        if session[session["active"]]["quote"] != "..." or manual_test:
            bot_response = f"Based on the images you provided, the quotation is {session[session['active']]['quote']}, please let us know once the patient agrees to it?"
            session['current_stage'] = 'scheduling_quote_confirm'
            session['last_question'] = bot_response
        else:
            bot_response = "We are still reviewing the quote will get back to you shortly, till then woudl you like to do anything else perhap submit an another case or track an existing case"


    elif session['current_stage'] == 'scheduling_quote_confirm':
        print("Processing in 'scheduling_quote_confirm' stage...")
        confirmation_response = confirm_chain.invoke({"input": message_body, "question": session['last_question']})
        confirmation_response = confirmation_response.lower()
        print(f"Confirmation response: {confirmation_response}")
        if "unknown" in confirmation_response:
            pass
        elif "no" in confirmation_response:
            bot_response = "Thank you for contacting 3D-Align."
            #session['current_stage'] = 'end_session'
            print(f"Transitioned to 'end_session'. Bot response: {bot_response}")
        elif "yes" in confirmation_response:
            bot_response = "Great...Now please let us know the patient name"
            session['current_stage'] = 'fetching_name'
            session['last_question'] = bot_response

    elif session['current_stage'] == 'fetching_name' :
        print("stage : getname")
        get_name = llm.invoke(f"""
You are an AI assistant.

The user was asked to provide the patient's name. Their response was:
"{message_body}"

Your task:
- Extract the patient's **full name** from the response.
- your response should be **only the name** as plain text, with no extra words or formatting.
- If a name cannot be confidently identified, return a message that starts with the backtick symbol (`) and politely ask the user to provide the full name again.
""").content

        print(get_name)
        if '`' in get_name :
            bot_response = get_name
        else:
            # --- Google Drive folder rename logic ---
            try:
                from mainlogic import rename_patient_folder
                active_caseid = session['active']
                doc_name = session.get('name', None) or user_id  # fallback to user_id if not set
                old_patient_name = active_caseid
                new_patient_name = get_name
                # Only rename if the old name is still the caseid (i.e., not already renamed)
                if session[active_caseid]['name'] == old_patient_name:
                    rename_patient_folder(doc_name, old_patient_name, new_patient_name)
            except Exception as e:
                print(f"[WARN] Could not rename Google Drive folder: {e}")
            session[session['active']]['name'] = get_name
            get_db_ref().child('namebook').child(session['active']).set(get_name)
            message_body = 'unrelated'
            session['current_stage'] = 'choose'

    if session['current_stage'] == 'choose' :
        reply = choose_chain.invoke({"input":message_body})
        if 'submit_scan' in reply:
            session['current_stage'] = 'fetch_scan'
            bot_response = f"Send Intraroral Scan of {session[session['active']]['name']} on 3d.alignsolutions@gmail.com or here through whatsapp"
        elif 'schedule_scan' in reply:
            session['current_stage'] = 'scheduling_appointment'
            message_body = "need to schedule scan"
        else :
            temp = {"name" : "proceed3"}
            bot_response = 'Please choose how you would like to proceeed further ?'
    
    if session['current_stage'] == 'scheduling_appointment':
        print("Processing in 'scheduling_appointment' stage...")
        sched_prompt = hub.pull("hwchase17/structured-chat-agent") + """

You are a friendly and helpful assistant responsible for scheduling 3D-Align scanning appointments.

Behavior:
- Always respond only in valid JSON.
- Never write any text outside JSON—no thoughts, explanations, markdown, or formatting.
- Never use <think>, backticks, markdown lists, or headers.
- Each response must strictly follow the JSON format:
  {{
    "action": "Final Answer",
    "action_input": "your message to user"
  }}

Your Role:
Guide the user step by step to book a 3D-Align scan by following this process:

---

Step 1: Ask for Scan Date and Time
- First, say:
  "When would you like to schedule your scan? Please share the preferred date and time in ISO format, like 2025-06-12T15:30."

- Do not continue until the user provides a valid ISO 8601 date and time.

Once you get that:

- Say:
  "Thanks! And where will the scan take place? You can share the clinic address or send your location."

- Wait until both date/time and location are provided before continuing.

---

Step 2: Check Availability
- After receiving both date/time and location:
  - Convert the provided date and time to ISO 8601 format.
  - Use the `CheckCalendarAvailability` tool with just the ISO datetime as input.

---

Step 3: Confirm with User
- If the slot is available:
  - Say: "The slot is available."
  - Then ask: "Would you like me to book the appointment for this date, time, and location?"

- Do not proceed without user confirmation.

---

Step 4: Book the Appointment
- If the user confirms:
  - Call `BookCalendarAppointment` with this string format:
    "<iso_datetime>,<location>"

  - If the location is GPS coordinates, convert it to:
    "https://maps.google.com/?q=<latitude>,<longitude>"

- If successful, return this final response in JSON:
  {{
    "action": "Final Answer",
    "action_input": "2025-06-12,15:30,https://maps.google.com/?q=19.0760,72.8777,True"
  }}

---

Step 5: Handle Unavailability
- If the slot is NOT available:
  - Say: "That slot is not available."
  - Go back to Step 1 and politely ask the user to suggest a new date and time.

---

Important Rules:
- Never assume anything. Always wait for the user to provide clear information.
- Ask only one question at a time.
- Keep each message short, clear, and polite.
- Do not suggest alternate times.
- Do not continue unless required data is present.
- Final output must always be valid JSON with only `action` and `action_input` keys.

"""

        sched_agent = create_structured_chat_agent(llm, tools=scheduling_tools, prompt=sched_prompt)
        sched_executor = AgentExecutor.from_agent_and_tools(
            agent=sched_agent, tools=scheduling_tools, memory=session['sched_memory'], handle_parsing_errors=True, verbose=True
        )

        # The first message to this agent will be from the user, following the bot's "Great! Let's schedule..." message
        # The agent will then use its instructions (in sched_initial_message) to ask for time and location.
        try:
            response = sched_executor.invoke({"input": message_body})["output"]
            if response.strip().split(',')[-1] == "True":
                bot_response = f"""This is to inform you that Intraoral Scan booked for 

Patient Name :- {session[session['active']]['name']}

Date :- {response.strip().split(',')[0]}
Time :-{response.strip().split(',')[1]}
Location :- {response.strip().split(',')[2]}

Please Note :-
Any changes in intraoral scan schedule has to be made 24 hours prior or else scan cancellation charges would be levied as applicable. 
No Cancellation charges if intimated 24 hours prior. 
Intraoral Scan once taken will be consider to go for aligner treatment plan simulation and simulation charges would be levied as applicable. In case of any query please feel free to contact."""

            else:
                bot_response =response
        except Exception as e:
            print(f"Error during scheduling agent invocation: {e}")
            bot_response = "An error occurred during scheduling. Please try again."
   
    elif session['current_stage'] == 'fetch_scan' :
        print("Processing in 'awaiting_stl_files' stage...")
        session['stl_file_count'] = session.get('stl_file_count', 0)
        if num_media > 0:
            print(f"Received {num_media} media items. Checking for STL files...")
            successful_forwards = 0

            for url, content_type in zip(media_urls, media_content_types):
                print(content_type)
                if content_type in ["application/sla", "model/stl","application/vnd.ms-pki.stl"]:
                    if forward_media_to_number(url, user_id, 'intraoral_scan'):
                        successful_forwards += 1
                    else:
                        print(f"Failed to forward STL file: {url}")
                else:
                    print(f"Ignored non-STL file: {url} (Content-Type: {content_type})")
            session['stl_file_count'] = session.get('stl_file_count', 0) + successful_forwards

            if successful_forwards > 0:
                bot_response = (
                    f"I've successfully received {session['stl_file_count']} STL file(s). "
                    "Type 'DONE' when you're ready to proceed."
                )
            else:
                bot_response = (
                    "None of the files you sent appear to be valid STL files. "
                    "Please try again or type 'DONE' if you're finished."
                )
            print(f"Bot response in 'awaiting_stl_files': {bot_response}")

        elif message_body.lower() == 'done':
            print("User typed 'DONE' in 'awaiting_stl_files' stage.")
            if session['stl_file_count'] > 0 :
                session[session["active"]]['scan_recieved']=True
                session['stl_file_count'] = 0  # Reset counter
            else:
                bot_response = (
                    "You haven't submitted any valid STL files yet. "
                    "Please send at least one to continue."
                )
        
            session['current_stage'] = 'scan_confirm'
        else :
            bot_response = f"Send Intraroral Scan of {session[session['active']]['name']} on 3d.alignsolutions@gmail.com or here through whatsapp to proceed further"
        if session[session["active"]].get('scan_recieved'):
            bot_response = f"""We have received - Intraoral Scan / PVS Impression of your case 
Patient Name :- {session[session['active']]['name']}
Our 3D Align Team will be working on your case and will provide you Treatment Plan alongwith Simulations Videos within next 48 hours 
In case of any query please feel free to contact."""
    elif session['current_stage'] == 'scan_confirm' :
        reply = express_chain.invoke({'input' : message_body})
        if 'express' in reply :
            session[session['active']]['cat'] = 'express'
            bot_response = f"okay I have kept it in express category"
        elif 'normal' in reply:
            session[session['active']]['cat'] = 'normal'
            bot_response =f"no problem it is in normal category"
        else :
                bot_response = f"your case for {session[session['active']]['name']} is still under processing we will inform you once it is done. Thank you for using 3D-Align services. Have a great day!"
                session['current_stage'] = "case_tracking"

    elif session['current_stage'] == 'case_tracking':
        # Get the active case ID from session
        active_case_id = session.get('active')
        status = session.get(active_case_id, {}).get('status', 'unknown')
        if status == 'ApprovedForProduction':
            bot_response = f"We have started production for your case {session[active_case_id]['name']}. You will receive updates as your case progresses."
        elif status == 'FabricationStarted':
            bot_response = f"""This is to inform you that the process of Aligner Fabrication has been initiated for your case. 

Patient Name :- {session[active_case_id]['name']}

Dispatch details will soon be provided to you."""
        elif status == 'location_asked':
            if "https://www.google.com/maps?q=" in message_body:
                bot_response = f"Thank you! We have noted the location for delivery: {message_body}."
                session[active_case_id]['delivery_location'] = message_body
                session[active_case_id]['status'] = 'location_received'
            else:
                bot_response = "Please provide a valid location coordinates using location icon for the delivery location."
        elif status == 'location_received':
            bot_response = f"Thank you for providing the delivery location for your case {session[active_case_id]['name']}. We will dispatch your aligners to this address. -> {session[active_case_id]['delivery_location']}"
            session["current_stage"] = "end_session"
        elif status == 'dispatched':
            bot_response =f"""Thank you for your valuable support. 

Please take a note of details of your shipment :- 

Patient Name :- {session[active_case_id]['name']}
Consignment Items :- {session[active_case_id].get('consignment_items', 'Not specified')}
Tracking ID :- {session[active_case_id].get('tracking_id', 'Not specified')}
Tracking Site :- {session[active_case_id].get('tracking_site', 'Not specified')}

In case if shipment is not delivered to you within 2-4 days of dispatch than please revert back to us. 
"""
        elif status == 'fit_confirmation':
            bot_response = """We would like to know the fit of training aligner sent to you for 
Patient Name :- 

Also please let us know whether we should go ahead for the fabrication of remaining sets of aligner ? 

Please Note :- 
Remaining sets of aligner will be dispatched within a week upon confirmation received for the case. 
"""         
            reply = confirm_chain.invoke({"input": message_body, "question": bot_response})
            reply = reply.lower()
            if "yes" in reply:
                session[active_case_id]['status'] = 'preference_asked'
                temp = {"name":"typedispatch","variables":[
                    {"type": "text" , "text":session[active_case_id]['name']}
                ]}
                session["current_stage"] = "end_session"
            elif "no" in reply:
                bot_response = f"Okay, we will not proceed with the fabrication of remaining aligners for {session[active_case_id]['name']}."
                session["current_stage"] = "end_session"
            else :
                bot_response = "Please respond with 'yes' or 'no'."
        elif status == 'preference_asked':
            if "full" in message_body.lower():
                session[active_case_id]['preference'] = 'full'
                bot_response = f"Thank you! We will proceed with the full fabrication for {session[active_case_id]['name']}."
                session[active_case_id]['status'] = 'fabrication_started'
                session["current_stage"] = "end_session"
            elif "phase" in message_body.lower():
                session[active_case_id]['preference'] = 'partial'
                bot_response = f"Thank you! We will proceed with the partial fabrication for {session[active_case_id]['name']}."
                session[active_case_id]['status'] = 'fabrication_started'
                session["current_stage"] = "end_session"
            else:
                bot_response = "Please specify if you want to proceed with 'full dispatch' or 'phase dispatch' fabrication for the remaining aligners."
        elif status == 'fabrication_started':
            bot_response = f"""This is to inform you that the process of Aligner Fabrication has been initiated for {session[active_case_id]['name']}."""
            session['current_stage'] = "end_session"
        elif status == 'unknown':
             bot_response = f"your case for {session[session['active']]['name']} is still under processing we will inform you once it is done. Thank you for using 3D-Align services. Have a great day!"

    if session['current_stage'] == 'end_session':
        session['active'] = ""
        session['last_question'] = ""
        session['image_count'] = 0
        session['stl_file_count'] = 0
        session['current_stage'] = "intent"

    print(f"Final bot_response to be sent: '{bot_response}'")
    print(f"--- End handle_bot_logic ---\n")
    if isinstance(session.get('sched_memory'), ConversationBufferMemory):
        session['sched_memory'] = ls(session['sched_memory'])
        print("Sched memory serialized (object -> list).")
    else:
        # Ensure it's a serializable format if it's not a memory object
        # e.g., if it was initialized as False or cleared
        session['sched_memory'] = [] # Store as empty list instead of False for consistency
        print("Sched memory set to empty list for saving.")

    if isinstance(session.get('auth_memory'), ConversationBufferMemory):
        session['auth_memory'] = ls(session['auth_memory'])
        print("Auth memory serialized (object -> list).")
    else:
        session['auth_memory'] = [] # Store as empty list
        print("Auth memory set to empty list for saving.")

    session['calendar_service'] = session.get('calendar_service', True)
    update_db(user_id,session)
    print(f"exited_handlebot with : {bot_response}")
    return temp,bot_response


# Get downloadable media URL from media ID
def get_media_url(media_id):
    url = f"https://graph.facebook.com/v18.0/{media_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.get(url, headers=headers)
    return response.json().get("url", "")

# Send text message
def send_whatsapp_text(to, body):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    res = requests.post(url, headers=headers, json=payload)
    print("📤 Text sent:", res.status_code, res.text)

# Send template message
def send_whatsapp_template(to,params):
    print("Preparing to send template with:", params)
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": params.get("name"),  # Replace with your actual template name
            "language": {"code": "en_IN"},
            "components": [
                {
                    "type": 'body',
                    "parameters": params.get("variables",[]) 
                },
                {
                    "type": 'header',
                    "parameters": params.get("variables_head",[]) 
                }
            ] 
        }
    }
    res = requests.post(url, headers=headers, json=payload)
    print("📤 Template sent:", res.status_code, res.text)
    try:
        res_json = res.json()
        if res.status_code == 200 and "messages" in res_json:
            message_id = res_json["messages"][0]["id"]
            return message_id
        else:
            return None
    except Exception as e:
        print(f"❌ Error parsing response or extracting message ID: {e}")
        return None

# ==============================================================================
# DENTAL ALIGNER WORKFLOW INTEGRATION
# ==============================================================================

# ✅ MAIN WHATSAPP CLOUD API WEBHOOK
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    # Initialize lazy-loaded services
    get_db_ref()  # Initialize Firebase
    get_user_sessions_fb()  # Initialize user sessions reference
    
    data = request.get_json()
    try:
        # Navigate the webhook payload structure safely
        entry = data.get("entry", [])[0] if data.get("entry") else None
        if not entry:
            print("No 'entry' in webhook data. Skipping.")
            return "No entry", 200

        change = entry.get("changes", [])[0] if entry.get("changes") else None
        if not change:
            print("No 'changes' in webhook entry. Skipping.")
            return "No changes", 200

        value = change.get("value", {})

        # --- CRITICAL FILTERING LOGIC ---
        # Only process if it's an actual 'messages' array and not a 'statuses' array
        if 'messages' in value and value['messages']:
            # This is an actual incoming user message
            message = value['messages'][0]
            contacts = value.get("contacts", []) # Get contacts for sender_id
            msg_id = message.get("id")
            msg_ref = get_db_ref().child("processed_messages").child(msg_id.replace('.','-'))

            if msg_ref.get() is not None:
                print(f"[DEDUPLICATION] Message ID {msg_id} already processed. Skipping.")
                return "Duplicate message", 200

            # Store it with timestamp
            msg_ref.set({
                "created_at": int(time.time())  # Store current UNIX time
            })

            if not contacts:
                print("No 'contacts' in message event. Skipping.")
                return "No contacts in message event", 200 # Should ideally not happen for valid messages

            contact = contacts[0]
            sender_id = f"whatsapp:+{contact['wa_id']}" # Correct sender_id format
            incoming_msg = ""
            media_urls = []
            media_content_types = []
            num_media = 0

            msg_type = message.get("type")

            if msg_type == "text":
                incoming_msg = message["text"]["body"]
            elif msg_type == "button" :
                incoming_msg = message["button"]["text"]
            elif msg_type in ["image", "document", "audio", "video", "sticker"]:
                media_info = message[msg_type]
                media_id = media_info.get("id")
                media_url = get_media_url(media_id)
                media_urls.append(media_url)
                media_content_types.append(media_info.get("mime_type", "application/octet-stream"))
                num_media = 1
                incoming_msg = f"[{msg_type.capitalize()} received]"
            elif msg_type == "location":
                latitude = message["location"]["latitude"]
                longitude = message["location"]["longitude"]
                incoming_msg = f"https://www.google.com/maps?q={latitude},{longitude}"
            # Add other message types (audio, video, document, etc.) as needed

            # --- SESSION HANDLING ---
            user_sessions_fb = get_user_sessions_fb()
            session = user_sessions_fb.child(sender_id).get()

            if session is None:
                initialize_user_session(sender_id)
                session = user_sessions_fb.child(sender_id).get() # Re-fetch newly created session
                # If you want to send a welcome message for new users only once, do it here
                # send_whatsapp_text(sender_id, "Welcome to 3D-Align! Please provide your full name to get started.")
            print(data)
            # --- CALL MAIN BOT LOGIC (Synchronously) ---
            temp_status, bot_response_content = handle_bot_logic(
                sender_id, incoming_msg, num_media, media_urls, media_content_types, session
            )
            print(f"handle_bot_logic returned: {temp_status}, '{bot_response_content}'")

            # Check if this message should be processed by the production workflow
            '''if should_process_with_workflow(session, incoming_msg):
                workflow_result = process_message_with_workflow(sender_id, incoming_msg, session)
                if workflow_result.get("messages_to_send"):
                    # Send workflow messages instead of bot response
                    for message in workflow_result["messages_to_send"]:
                        send_whatsapp_text(message["recipient_id"], message["content"])
                    return "EVENT_RECEIVED", 200'''

            # --- Send Bot's Reply ---
            if sender_id != "whatsapp:+917801833884":
                parent_msg_id = message.get("context", {}).get("id", None)
                print(parent_msg_id)
                handle_production(parent_msg_id,incoming_msg)
            else :
                if temp_status:
                    send_whatsapp_template(sender_id,temp_status)
                else:
                    send_whatsapp_text(sender_id, bot_response_content)

        elif 'statuses' in value and value['statuses']:
            # This is a message status update (e.g., delivered, read)
            status_update = value['statuses'][0]
            print(f"Received message status update: ID={status_update.get('id')}, Status={status_update.get('status')}")
            # Do NOT call handle_bot_logic for status updates.
            # You can add specific logging or database updates for message statuses here if needed.
        else:
            print(f"Webhook event received with no 'messages' or 'statuses' in value, or empty arrays. Skipping. Value: {value}")

    except IndexError:
        # Handles cases where 'entry' or 'changes' might be empty lists
        print("Webhook data structure missing expected 'entry' or 'changes' element. Skipping.")
    except Exception as e:
        print(f"❌ Error processing webhook data: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging

    return "EVENT_RECEIVED", 200


# ==============================================================================
# 5. RUN THE FLASK APP
# ==============================================================================
if __name__ == "__main__":
    if not os.path.exists('client_secret.json'):
        print("Error: 'client_secret.json' not found. Please download it from Google Cloud Console.")
        exit()

    print("Initializing Google Calendar service (may require browser authentication)...")
    temp_service = get_calendar_service_oauth()
    if not temp_service:
        print("Failed to initialize Google Calendar service. The bot may not function correctly.")
    else:
        print("Google Calendar service ready.")

    print("Starting Flask server. Your Twilio webhook URL will be something like: YOUR_NGROK_URL/whatsapp")
    if not os.getenv("NGROK_URL"):
        print("\n*** IMPORTANT: NGROK_URL environment variable is NOT set. ***")
        print("   Media forwarding will likely FAIL as Twilio cannot access localhost.")
        print("   Please run ngrok (e.g., `ngrok http 5000`) and set NGROK_URL in your .env file")
        print("   to the HTTPS URL ngrok provides (e.g., https://xxxxxxxxxxxx.ngrok-free.app).\n")
    manual_test = False
    while manual_test:
        sender_id = "whatsapp:+917801831000"
        num_media = 0
        media_urls =[]
        session = user_sessions_fb.child(sender_id).get()
        if session is not None :
            incoming_msg = input("user :")
            print(session)
            session = dict(session)
            media_content_types = ["application/sla"]
            bot_response = handle_bot_logic(sender_id, incoming_msg, num_media, media_urls, media_content_types, session )
        else :
            initialize_user_session(sender_id)
    start_localtunnel()
    app.run(port=5000,debug=True)