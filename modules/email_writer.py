import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from utils.auth import authenticate


def create_message(to, subject, message_text, message_id=None):
    message = MIMEText(message_text)

    message['to'] = to
    message['subject'] = subject

    if message_id:
        message['In-Reply-To'] = message_id
        message['References'] = message_id

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw}


def send_email(to, subject, body, thread_id=None, message_id=None):
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)

    message = create_message(to, subject, body, message_id)

    send_body = message

    if thread_id:
        send_body['threadId'] = thread_id

    service.users().messages().send(
        userId='me',
        body=send_body
    ).execute()

    print("\n✅ Email sent successfully!")