# This script integrates with the Gmail API to fetch, summarize, and manage emails. 
# It includes functions for extracting email bodies, summarizing content using OpenAI, and deleting emails.
import os
import os.path
import sys
import requests
import email.parser
from datetime import datetime, timedelta
from openai import OpenAI
from base64 import urlsafe_b64encode, urlsafe_b64decode # to decode/encode email content
# for Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def get_email_body(msg_payload):
  """
  Extract the plain text body from an email message.
  """
  body_text = ''
  if 'parts' in msg_payload: # this means there's multiparts
    for part in msg_payload['parts']:
      if part['mimeType'] == 'text/plain':
        data = part['body'].get('data')
        if data:
          #base64url decode
          body_text += urlsafe_b64decode(data).decode('utf-8')
          # # base64url decode with padding
          # padded = data + '=' * (-len(data) % 4)
          # body_text += urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8', errors='replace')

      elif part['mimeType'].startswith('multipart/'):
        # recursively extract from subparts
        body_text += get_email_body(part)
  else: # single part message
    if msg_payload['mimeType'] == 'text/plain' :
      data = msg_payload['body']['data']
      if data:
        #base64 decode
        body_text += urlsafe_b64decode(data).decode('utf-8')
        # base64url decode with padding
        # padded = data + '=' * (-len(data) % 4)
        # body_text += urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8', errors='replace')
  return body_text

def full_emails(service):
    """
    Fetches all emails from the previous day and saves their full content.
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    query = f'after:{yesterday}'
    
    email_list = []
    
    # Get a list of message IDs from the previous day
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])
    
    if not messages:
        print("No emails found for yesterday.")
        return []
        
    for message in messages:
        # For each email message ID, make a second API call to get the full message
        msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
        
        email_data = {}
        payload = msg['payload']
        headers = payload['headers']
        
        # Extract headers (subject, from, etc.)
        for header in headers:
            if header['name'] in ['From', 'Subject']:
                email_data[header['name']] = header['value']
        
        # Get the full email body
        email_data['body'] = get_email_body(payload)
        
        email_list.append(email_data)
        
    return email_list

content = """

Dear Residents,

This is a friendly reminder that towing enforcement will begin tonight. Please make sure your Green Parking Pass, provided at move-in, is clearly visible in your windshield at all times.

Additionally, please remember that the first-floor parking area is reserved for retail parking only. All residents must park beyond the gate in the designated residential parking areas to avoid being towed.

Any vehicle parked in the retail area or without a visible Green Parking Pass will be subject to towing at the owner’s expense.

Thank you for your cooperation and for helping us keep the community parking organized and accessible for everyone.

Warm regards,
One NoDA Park Team

"""

def summarize_email(content):
  """
  Summarizes email content to 1-2 lines using OpenAI API.
  """
  API_KEY = OPEN_API_KEY
  client = OpenAI(api_key=os.getenv(API_KEY))
  summary = client.chat.completions.create(
      model="gpt-4o",
      messages=[
          {"role": "system", "content": "You are an expert email summarizer."},
          {"role": "user", "content": f"Summarize the following email content in 1-2 lines:\n\n{content}"}
      ],
      max_completion_tokens=100,
      temperature=0.5,
  )
  return summary.choices[0].message.content.strip()

def email_urgency_classifier(email_contents):
  pass

def delete_emails(email_ids):
  trash_ids = {'ids': email_ids}
  for id in trash_ids:
     service.users().messages().trash(userId='me', id=id).execute()
  pass

def main():
  """
  Shows basic usage of the Gmail API.
  Lists the user's Gmail labels.
  """
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
