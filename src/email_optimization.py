"""
Email summarizer and organizer pipeline using LLM APIs.
Load → organize → delete unwanted emails → summarize inbox .

Before running this:
1. Make sure googleapi is connected and token.json is active.
2. Set OPENAI_API_KEY in your environment variables and save it in a .env file for local dev.
https://pypi.org/project/python-dotenv/

Example usage:
source .venv/bin/activate # activate virtual environment
pip install -r requirements.txt # install dependencies

# Summarize only (previous day)
python3 src/email_optimization.py --summarize --no-trash

# Trash only (custom timeline)
python3 src/email_optimization.py --no-summarize --trash --trash-query "in:inbox newer_than:30d"

# Both (summaries from yesterday, trash from custom query)
python3 src/email_optimization.py --summarize --trash --trash-query "in:inbox after:2026/02/01 before:2026/03/01"

**If you get a refresh token error, delete token.json and re-run to re-authenticate.

"""

import os
import os.path
import sys
import time
import json
import argparse

from datetime import datetime, date, timedelta, timezone
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import OpenAI
from logging_utils import setup_logger, log_event, log_timing
from base64 import urlsafe_b64encode, urlsafe_b64decode # to decode/encode email content
# for Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.message import EmailMessage

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

@dataclass
class EmailRecord:
    msg_id: str
    headers: Dict[str, str]
    subject: Optional[str]
    sender: Optional[str]
    body: str
    labels: List[str]

load_dotenv() # load environmental variables
logger = setup_logger() # set up logging

STATE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "cleanup_state.json")
)
SUMMARY_TO = os.getenv("SUMMARY_TO")

# Helper functions for the project
def _load_state(path):
  try:
    with open(path, "r") as handle:
      return json.load(handle)
  except FileNotFoundError:
    return {}
  except json.JSONDecodeError:
    return {}

def _save_state(path, state):
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w") as handle:
    json.dump(state, handle, indent=2, sort_keys=True)

def _parse_utc(ts):
  if not ts:
    return None
  try:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
      return parsed.replace(tzinfo=timezone.utc)
    return parsed
  except ValueError:
    return None

def build_previous_day_query(base_query="in:inbox"):
  today = date.today()
  yesterday = today - timedelta(days=1)
  return f"{base_query} after:{yesterday:%Y/%m/%d} before:{today:%Y/%m/%d}"

class GmailClient:
    """
    Class for handling Gmail API
    """
    def __init__(self, service, logger):
        self.service = service
        self.logger = logger

    def list_message_ids(
        self,
        query,
        label_ids=None,
        include_spam_trash=False,
        page_size=500,
        max_retries=5,
    ):
        """
        Gets message ids of emails while handling pagination and idempotency
        """
        msg_ids = []
        page_token = None

        with log_timing(
            self.logger,
            "gmail.list",
            query=query,
            label_ids=label_ids,
            include_spam_trash=include_spam_trash,
        ):
            while True:
                for attempt in range(max_retries):
                    try:
                        list_kwargs = {
                            "userId": "me",
                            "q": query,
                            "includeSpamTrash": include_spam_trash,
                            "pageToken": page_token,
                            "maxResults": page_size,
                        }
                        if label_ids is not None:
                            list_kwargs["labelIds"] = label_ids

                        resp = (
                            self.service.users()
                            .messages()
                            .list(**list_kwargs)
                            .execute()
                        )
                        break  # success, stop retrying..
                    except HttpError as e:
                        status = getattr(e, "resp", None) and e.resp.status
                        if status in (429, 500, 503) and attempt < max_retries - 1:
                            # 429 - too many requests
                            # 500 - internal server error
                            # 503 - service unavailable(temp overload or scheduled maintainance)
                            time.sleep(2 ** attempt)
                            continue
                        raise

                messages = resp.get("messages", [])
                msg_ids.extend(m["id"] for m in messages)

                page_token = resp.get("nextPageToken")
                if not page_token:
                    break

        log_event(self.logger, "gmail.list.complete", query=query, count=len(msg_ids))

        return msg_ids

    def fetch_messages(self, msg_ids, fmt="full"):
        """
        Fetch raw Gmail messages for a list of IDs.
        """
        messages = []
        for msg_id in msg_ids:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format=fmt)
                .execute()
            )
            messages.append(msg)
        return messages

    def trash_message(self, msg_id):
        self.service.users().messages().trash(userId="me", id=msg_id).execute()

    def batch_trash(self, msg_ids, remove_labels=None):
        remove_labels = remove_labels or []
        self.service.users().messages().batchModify(
            userId="me",
            body={
                "ids": msg_ids,
                "addLabelIds": ["TRASH"],
                "removeLabelIds": remove_labels,
            },
        ).execute()

    def trash_category(self, category):
        """
        Move spam, promotion, and social emails to the trash folder.
        """
        try:
            if category == "spam":
                query = "in:spam"
            else:
                query = f"category:{category}"

            log_event(self.logger, "trash.start", category=category)

            msg_ids = self.list_message_ids(query)
            if not msg_ids:
                log_event(self.logger, "trash.skip", category=category, reason="empty")
                return

            trashed_emails = 0
            for i in range(0, len(msg_ids), 1000):
                batch = msg_ids[i : i + 1000]
                remove_labels = ["SPAM"] if category == "spam" else []
                self.batch_trash(batch, remove_labels=remove_labels)
                trashed_emails += len(batch)
                log_event(
                    self.logger,
                    "trash.progress",
                    category=category,
                    trashed=trashed_emails,
                )

            log_event(self.logger, "trash.complete", category=category, trashed=trashed_emails)

        except HttpError as error:
            log_event(self.logger, "trash.error", category=category, error=str(error))

    def send_email(self, to_addr, subject, body):
        msg = EmailMessage()
        msg["To"] = to_addr
        msg["From"] = "me"
        msg["Subject"] = subject
        msg.set_content(body)
        raw = urlsafe_b64encode(msg.as_bytes()).decode()
        self.service.users().messages().send(userId="me", body={"raw": raw}).execute()


class EmailSummarizer:
    """
    Class for summarizing emails
    """
    def __init__(self, logger, openai_api_key=None):
        self.logger = logger
        self.openai_api_key = openai_api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set")
            self._client = OpenAI(api_key=api_key)
        return self._client

    def summarize(self, content):
        """
        Summarizes email content to 1-2 lines using OpenAI API.
        """
        client = self._get_client()
        with log_timing(self.logger, "summarize", model="gpt-5-nano"):
            response = client.chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert email summarizer. Produce 1-2 concise lines. "
                            "Focus on the core ask, deadline, and who it impacts. "
                            "Ignore signatures, legal disclaimers, and repetitive boilerplate. "
                            "Do not quote the email or add new info."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Summarize this email:\n"
                            "### EMAIL START\n"
                            f"{content}\n"
                            "### EMAIL END"
                        ),
                    },
                ],
                max_completion_tokens=536,
                temperature=1,
            )
        summary = response.choices[0].message.content.strip()
        log_event(self.logger, "summarize.complete", summary_chars=len(summary))
        return summary


class EmailPipeline:
    """
    Class where the project implementation happens.
    """
    CATEGORY_TRASH = ("promotions", "spam", "social")

    def __init__(self, gmail_client, summarizer, logger, summary_to=None):
        self.gmail = gmail_client
        self.summarizer = summarizer
        self.logger = logger
        self.summary_to = summary_to

    @staticmethod
    def get_email_body(msg_payload):
        """
        Extract the plain text body from an email message.
        """
        body_text = ""
        if "parts" in msg_payload:  # this means there's multiparts
            for part in msg_payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data")
                    if data:
                        # base64url decode
                        body_text += urlsafe_b64decode(data).decode("utf-8")
                elif part["mimeType"].startswith("multipart/"):
                    # recursively extract from subparts
                    body_text += EmailPipeline.get_email_body(part)
        else:  # single part message
            if msg_payload["mimeType"] == "text/plain":
                data = msg_payload["body"]["data"]
                if data:
                    # base64 decode
                    body_text += urlsafe_b64decode(data).decode("utf-8")
        return body_text

    def parse_message(self, msg):
        """
        Convert a raw Gmail message into a normalized dict and save it to our EmailRecord dataclass.
        """
        payload = msg["payload"]
        headers = {h["name"]: h["value"] for h in payload["headers"]}
        return EmailRecord(
            msg_id=msg["id"],
            headers=headers,
            subject=headers.get("Subject"),
            sender=headers.get("From"),
            body=self.get_email_body(payload),
            labels=msg.get("labelIds", []),
        )

    def get_full_emails(self):
        """
        Fetches all emails from the previous day and saves their full content.
        """
        days = (datetime.now() - timedelta(days=1)).strftime("%Y/%m/%d")
        # query = f'after:{days}'
        # TODO:
        # Add days or query choices as a cli argument, default to days = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
        query = "after:2025/03/11 before:2025/07/12"

        email_list = []

        # Get a list of message IDs from the previous day
        log_event(self.logger, "emails.fetch.start", query=query, label_ids=["INBOX"])
        msg_ids = self.gmail.list_message_ids(query, label_ids=["INBOX"])

        if not msg_ids:
            log_event(self.logger, "emails.none", scope="month_inbox")
            return []

        raw_msgs = self.gmail.fetch_messages(msg_ids)
        for msg in raw_msgs:
            email_list.append(self.parse_message(msg))

        log_event(self.logger, "emails.fetch.complete", count=len(email_list))
        return email_list

    def should_trash_notification(self, email, log_match=True):
        """
        Rules to send to trash:
        - Sender contains "noreply" or "no-reply"
        - List-Unsubscribe header present
        """
        headers = email.headers
        sender = email.sender or ""
        sender_lower = sender.lower()
        is_noreply = ("no-reply" in sender_lower) or ("noreply" in sender_lower)
        has_list_unsubscribe = "List-Unsubscribe" in headers
        is_unwanted = is_noreply or has_list_unsubscribe
        if is_unwanted and log_match:
            reasons = []
            if is_noreply:
                reasons.append("noreply_sender")
            if has_list_unsubscribe:
                reasons.append("list_unsubscribe")
            log_event(
                self.logger,
                "unwanted_email.match",
                msg_id=email.msg_id,
                sender=email.sender,
                subject=email.subject,
                reasons=reasons,
            )
        return is_unwanted

    def plan_actions(self, email: EmailRecord, log_match=True) -> Dict[str, Any]:
        trash = self.should_trash_notification(email, log_match=log_match)
        body = email.body or ""
        summarize = (not trash) and bool(body.strip())
        return {
            "trash": trash,
            "summarize": summarize,
        }

    def apply_actions(self, email: EmailRecord, actions: Dict[str, Any]) -> None:
        # TODO: make sure apply_actions function can access msg_id
        if actions["trash"]:
            log_event(
                self.logger,
                "unwanted_email.trash",
                msg_id=email.msg_id,
                sender=email.sender,
                subject=email.subject,
            )
            self.gmail.trash_message(email.msg_id)

    @staticmethod
    def build_daily_digest(summaries, date_label):
        lines = [f"Daily Email Summary - {date_label}", "-" * 40]
        for i, item in enumerate(summaries, 1):
            lines.append(f"{i}. {item['subject']} - {item['summary']}")
        return "\n".join(lines)

    def trash_categories(self) -> None:
        for category in self.CATEGORY_TRASH:
            self.gmail.trash_category(category)
            time.sleep(0.5)  # Tiny delay for clarity

    def trash_unwanted(self, query: str) -> None:
        msg_ids = self.gmail.list_message_ids(query=query)
        raw_msgs = self.gmail.fetch_messages(msg_ids)

        log_event(self.logger, "unwanted_email.scan.start", query=query, count=len(raw_msgs))

        flagged = 0
        for msg in raw_msgs:
            email = self.parse_message(msg)
            if self.should_trash_notification(email, log_match=True):
                flagged += 1
                self.apply_actions(email, {"trash": True})

        log_event(self.logger, "trash.flagged.count", count=flagged, total=len(raw_msgs))

    def run_summary(self, query: str) -> None:
        if self.summarizer is None:
            raise ValueError("Summarizer is not configured")

        msg_ids = self.gmail.list_message_ids(query=query)
        raw_msgs = self.gmail.fetch_messages(msg_ids)

        log_event(self.logger, "email.summary.scan.start", query=query, count=len(raw_msgs))

        summaries = []
        for msg in raw_msgs:
            email = self.parse_message(msg)
            actions = self.plan_actions(email, log_match=False)
            actions["trash"] = False
            if actions.get("summarize"):
                summary = self.summarizer.summarize(email.body)
                summaries.append(
                    {
                        "subject": email.subject or "(no subject)",
                        "summary": summary,
                    }
                )

        if self.summary_to and summaries:
            date_label = datetime.now().strftime("%Y-%m-%d")
            digest = self.build_daily_digest(summaries, date_label)
            self.gmail.send_email(
                self.summary_to,
                f"Daily Email Summary - {date_label}",
                digest,
            )
            log_event(
                self.logger,
                "email.digest.sent",
                to_addr=self.summary_to,
                count=len(summaries),
                date_label=date_label,
            )
  

def main():
  parser = argparse.ArgumentParser(description="Email summarizer and cleanup pipeline")
  summarize_group = parser.add_mutually_exclusive_group()
  summarize_group.add_argument("--summarize", dest="summarize", action="store_true")
  summarize_group.add_argument("--no-summarize", dest="summarize", action="store_false")
  parser.set_defaults(summarize=True)

  trash_group = parser.add_mutually_exclusive_group()
  trash_group.add_argument("--trash", dest="trash", action="store_true")
  trash_group.add_argument("--no-trash", dest="trash", action="store_false")
  parser.set_defaults(trash=True)

  parser.add_argument("--trash-query", dest="trash_query", default=None)
  parser.add_argument("--summary-to", dest="summary_to", default=None)
  args = parser.parse_args()

  log_event(logger, "main.start")
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first time.

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
    service = build("gmail", "v1", credentials=creds) #generate a python object to call gmail api
    log_event(logger, "gmail.service.ready")
    label_results = service.users().labels().list(userId="me").execute()
    labels = label_results.get("labels", [])
    gmail_client = GmailClient(service, logger)
    # set up some variables
    summary_to = args.summary_to if args.summary_to is not None else SUMMARY_TO
    trash_query = args.trash_query or "in:inbox newer_than:30d"
    
    summarizer = (
        EmailSummarizer(logger, openai_api_key=os.getenv("OPENAI_API_KEY"))
        if args.summarize
        else None
    )

    pipeline = EmailPipeline(
        gmail_client,
        summarizer,
        logger,
        summary_to=summary_to,
    )

    # implement args if any
    if args.summarize:
      summary_query = build_previous_day_query("in:inbox")
      log_event(logger, "email.summary.query", query=summary_query)
      pipeline.run_summary(query=summary_query)

    if args.trash:
      log_event(logger, "unwanted_email.pipeline.query", query=trash_query)
      pipeline.trash_categories()
      pipeline.trash_unwanted(query=trash_query)


    log_event(logger, "pipeline.complete")


  except HttpError as error:
    log_event(logger, "main.error", error=str(error))


if __name__ == "__main__":
  try:
    main()
  except Exception as e:
    import traceback
    import sys
    log_event(logger, "main.exception", error=str(e))
    traceback.print_exc()
    sys.exit(1)
