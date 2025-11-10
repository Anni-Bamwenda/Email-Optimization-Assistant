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
