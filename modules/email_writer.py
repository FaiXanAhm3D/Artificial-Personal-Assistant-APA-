import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from utils.auth import authenticate


def create_message(to, subject, message_text):
    message = MIMEText(message_text)
    message['to'] = to
    message['subject'] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw}


def send_email(to, subject, body):
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)

    message = create_message(to, subject, body)

    service.users().messages().send(
        userId='me',
        body=message
    ).execute()

    print("\n✅ Email sent successfully!")