import os.path
import html
import re
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def main():
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    results = service.users().messages().list(userId='me', maxResults=5).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No messages found.")
        return

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()

        payload = msg_data['payload']
        headers = payload.get("headers")

        subject = ""
        sender = ""

        for header in headers:
            if header['name'] == 'Subject':
                subject = header['value']
            if header['name'] == 'From':
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
            body = html.unescape(body) # Fix HTML entities (&#39; → ')
            body = re.sub('<.*?>', '', body) # Remove HTML tags

        print("\n==============================")
        print(f"📩 From: {sender}")
        print(f"📌 Subject: {subject}")
        print(f"📝 Summary:\n{body[:300]}")  # limit to first 500 chars

if __name__ == '__main__':
    main()