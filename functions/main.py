# functions/main.py

from firebase_functions import https_fn

# Import the Flask app objects from your existing files
from server import app as whatsapp_bot_app
from portal import app as admin_portal_app

# Define ALL secrets your apps need.
# Firebase will load these from Secret Manager into the environment.
# In functions/main.py

# Remove the Twilio lines from this list
REQUIRED_SECRETS = [
    "OPENROUTER_API_KEY",
    "WHATSAPP_ACCESS_TOKEN", # This is your 'ACCESS_TOKEN' from server.py
    "DATABASE_URL",
    "PORTER_API_KEY",
    "ACESS", # This is the token from portal.py
]

# --- Cloud Function for the WhatsApp Bot ---
@https_fn.on_request(secrets=REQUIRED_SECRETS)
def bot_webhook(request: https_fn.Request):
    """ Routes incoming requests to the bot's Flask app (server.py). """
    # Initialize lazy-loaded services when the function is called
    from server import get_firebase_app, get_llm
    get_firebase_app()  # Initialize Firebase
    get_llm()  # Initialize LLM
    
    with whatsapp_bot_app.request_context(request.environ):
        return whatsapp_bot_app.full_dispatch_request()

# --- Cloud Function for the Admin Portal ---
@https_fn.on_request(secrets=REQUIRED_SECRETS)
def portal(request: https_fn.Request):
    """ Serves the HTML and handles forms for the admin web portal (portal.py). """
    # Initialize lazy-loaded services when the function is called
    from portal import get_firebase_app
    get_firebase_app()  # Initialize Firebase
    
    with admin_portal_app.request_context(request.environ):
        return admin_portal_app.full_dispatch_request()