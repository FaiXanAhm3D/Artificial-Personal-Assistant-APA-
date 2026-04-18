import os.path
import html
import re
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from modules.email_writer import send_email
from modules.email_ai import analyze_email

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

from googleapiclient.discovery import build
from utils.auth import authenticate





def read_emails():
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)

    results = service.users().messages().list(
    userId='me',
    labelIds=['INBOX'],
    maxResults=5).execute()
    messages = results.get('messages', [])

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()

        payload = msg_data['payload']
        headers = payload.get("headers")

        message_id = ""
        thread_id = msg_data.get("threadId")
        subject = ""
        sender = ""

        for header in headers:
            name = header['name'].lower()

            if name == "message-id":
                message_id = header['value']

            elif name == "subject":
                subject = header['value']

            elif name == "from":
                sender = header['value']

                parts = payload.get("parts")
                body = ""

        if parts:
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    data = part['body']['data']
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break
        else:
            data = payload['body']['data']
            body = base64.urlsafe_b64decode(data).decode('utf-8')

        body = html.unescape(body)
        body = re.sub('<.*?>', '', body)
        
        analysis = analyze_email(body)
        
        summary = analysis["summary"]
        importance = analysis["importance"]
        reply = analysis["reply"]

        print("\n==============================")
        print(f"📩 From: {sender}")
        print(f"📌 Subject: {subject}")
        print(f"📌 Summary: {summary}")
        print(f"⚠️ Importance: {importance}")
        print(f"✉️ Suggested Reply: {reply}")

        if importance != "Low":
            choice = input("\nSend reply? (y/n): ").lower()

            if choice == "y":
                print("\n✏️ Edit reply (press Enter to keep original):")
                user_edit = input()

                final_reply = user_edit if user_edit.strip() != "" else reply

                email_match = re.search(r"<(.+?)>", sender)
                if email_match:
                    receiver_email = email_match.group(1)
                else:
                    receiver_email = sender

                send_email(
                    receiver_email,
                    f"Re: {subject}",
                    final_reply,
                    thread_id=thread_id,
                    message_id=message_id
                )    

