import os.path
import base64
import time
import html
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from modules.email_writer import send_email
from modules.email_ai import analyze_email
from modules.email_ai import generate_reply
from utils.auth import authenticate
from bs4 import BeautifulSoup

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']



def final_email_send(sender,subject,final_reply,thread_id,message_id):
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

def read_emails():
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)
    for i in range(3):
        try:
            results = service.users().messages().list(
            userId='me',
            labelIds=['INBOX'],
            maxResults=5).execute()
            messages = results.get('messages', [])
            break

        except Exception as e:
            print("⚠️ Network error, retrying...", e)
            time.sleep(2)
    else:
        print("❌ Failed to fetch emails after 3 attempts.")
        return

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
                    data = part['body'].get('data')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode('utf-8')
                        break
            
            if not body:
                for part in parts:
                    if part['mimeType'] == 'text/html':
                        data = part['body'].get('data')
                        if data:
                            html_body = base64.urlsafe_b64decode(data).decode('utf-8')
                            soup = BeautifulSoup(html_body, "html.parser")
                            for tag in soup(["script", "style", "head", "meta", "noscript"]): #removes unwanted element
                                tag.decompose()
                            body = soup.get_text(separator=" ")
                            body = re.sub(r'\s+', ' ', body).strip() #clean whitespaces
                            break
        else:
            data = payload['body']['data']
            if data:
                body = base64.urlsafe_b64decode(data).decode('utf-8')

        body = html.unescape(body)
        body = re.sub('<.*?>', '', body)
        
        analysis = analyze_email(body)
        
        summary = analysis["summary"]
        importance = analysis["importance"]
        
        print("\n==============================")
        print(f"📩 From: {sender}")
        print(f"📌 Subject: {subject}")
        print(f"📌 Summary: {summary}")
        print(f"⚠️ Importance: {importance}")

        print("\nOptions:")
        if importance == "High":
            print("1. Send suggested reply")
            print("2. Write a custom reply")
            print("3. Skip")

            choice = input("Enter chouce (1/2/3): ").strip()

            if choice == "1":
                reply = generate_reply(body)
                final_reply = reply

                if not final_reply or final_reply.lower().startswith("error"):
                    print("⚠️ Invalid reply. Skipping.")
                    continue
                else:
                    final_email_send(sender,subject,final_reply,thread_id,message_id)

            elif choice == "2":
                reply = generate_reply(body) 
                print(f"✉️ Suggested Reply: {reply}")

                print("\n✏️ Write your reply OR Press ENTER to send the suggested reply:")

                user_edit = input()

                final_reply = user_edit if user_edit.strip() != "" else reply

                if not final_reply or final_reply.lower().startswith("error"):
                    print("⚠️ Invalid reply. Skipping.")
                    continue
                else:
                    final_email_send(sender,subject,final_reply,thread_id,message_id)
            else:
                continue

        else:
            print("1. Write/Generate a reply")
            print("2. Skip")

            choice = input("Enter chouce (1/2): ").strip()

            if choice == "1":
                reply = generate_reply(body)
                print(f"✉️ Suggested Reply: {reply}")

                print("\n✏️ Write your reply OR Press ENTER to send the suggested reply:")
                user_edit = input()
                final_reply = user_edit if user_edit.strip() else reply

                if not final_reply or final_reply.lower().startswith("error"):
                    print("⚠️ Invalid reply. Skipping.")
                    continue
                else:
                    final_email_send(sender,subject,final_reply,thread_id,message_id)

            elif choice == "2":
                continue 

