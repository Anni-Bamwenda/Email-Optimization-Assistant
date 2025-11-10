import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openai import OpenAI

def main():
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "credentials.json", SCOPES
      )
      creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
      token.write(creds.to_json())

  try:
    # Call the Gmail API
    global service
    service = build("gmail", "v1", credentials=creds) #generate a python object to call gmail api
    label_results = service.users().labels().list(userId="me").execute()
    labels = label_results.get("labels", [])
    # get the emails from previous day
    emails = full_emails(service)
    print(f"Fetched {len(emails)} emails from yesterday.")
    summarize_email(content)
    print("Sample Summary:\n", summarize_email(content))
  

  except HttpError as error:
    # TODO(developer) - Handle errors from gmail API.
    print(f"An error occurred: {error}")

  


if __name__ == "__main__":
  print("Starting email_optimization.py......")
  try:
    main()
    print("Finished email_optimization.py.")
  except Exception as e:
    import traceback
    import sys
    print("Error running main:", e)
    traceback.print_exc()
    sys.exit(1)
