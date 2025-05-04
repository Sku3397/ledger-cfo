# extract_token.py
import pickle
import sys
import os

# Try importing google auth libraries, provide instructions if missing
try:
    from google.oauth2.credentials import Credentials
    from google.auth.exceptions import RefreshError
except ImportError:
    print("Error: Required Google libraries not found.")
    print("Please install them by running: pip install google-auth-oauthlib")
    sys.exit(1)

# Define the path to your token file
TOKEN_PATH = 'token.pickle'

# Check if the token file exists
if not os.path.exists(TOKEN_PATH):
    print(f"Error: {TOKEN_PATH} not found in the current directory ({os.getcwd()}).")
    print("Please ensure the token.pickle file is present before running this script.")
    sys.exit(1)

# Load the credentials from the pickle file
try:
    with open(TOKEN_PATH, 'rb') as token_file:
        creds = pickle.load(token_file)

    # Extract the refresh token
    refresh_token = None
    if isinstance(creds, Credentials):
        refresh_token = creds.refresh_token
    else:
        # Handle older pickle formats if necessary, though unlikely with recent library versions
        print(f"Warning: Loaded object from {TOKEN_PATH} is not a standard Credentials instance. Attempting to find refresh_token attribute.")
        if hasattr(creds, 'refresh_token'):
            refresh_token = creds.refresh_token

    if refresh_token:
        print("--- Extracted Gmail Refresh Token --- (Copy the line below)")
        print(refresh_token)
        print("-------------------------------------")
    else:
        print(f"Error: No refresh token found within {TOKEN_PATH}. Did the OAuth flow complete correctly and include offline access request?")

except FileNotFoundError:
    # This check is redundant due to the os.path.exists check above, but kept for robustness
    print(f"Error: {TOKEN_PATH} not found.")
except Exception as e:
    print(f"An error occurred loading or processing {TOKEN_PATH}: {e}")
    print("Ensure the file is a valid Google OAuth token pickle file.") 