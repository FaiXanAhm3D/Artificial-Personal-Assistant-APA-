import os.path
import html
import re
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

from googleapiclient.discovery import build
from utils.auth import authenticate
import base64
import html
import re


def read_emails():
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)

    results = service.users().messages().list(userId='me', maxResults=5).execute()
    messages = results.get('messages', [])

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()

        payload = msg_data['payload']
        headers = payload.get("headers")

        subject = ""
        sender = ""

        for header in headers:
            name = header['name'].lower()
            if name == 'subject':
                subject = header['value']
            elif name == 'from':
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

        print("\n==============================")
        print(f"📩 From: {sender}")
        print(f"📌 Subject: {subject}")
        print(f"📝 {body[:300]}")

if __name__ == '__main__':
    read_emails()