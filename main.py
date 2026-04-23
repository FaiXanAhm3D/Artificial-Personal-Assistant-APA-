from dotenv import load_dotenv
load_dotenv()

from modules.email_reader import read_emails
from modules.email_writer import send_email



def main():
    while True:
        print("\n===== APA Assistant =====")
        print("1. Read Emails")
        print("2. Send Email")
        print("3. Exit")

        choice = input("Enter choice: ")

        if choice == "1":
            read_emails()

        elif choice == "2":
            to = input("📧 Enter recipient: ")
            subject = input("📌 Enter subject: ")
            body = input("📝 Enter message: ")
            send_email(to, subject, body)

        elif choice == "3":
            print("Exiting...")
            print("Have a great day!")
            break

        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()