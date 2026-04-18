import os
from groq import Groq
from .base import BaseAI


class GroqAI(BaseAI):
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    def generate_reply(self, email_content):
        try:
            response = self.client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                
                    "role": "system",
                    "content": """You are a professional email assistant.

                Write a reply that:
                - Directly addresses the sender’s intent
                - Is polite and human-like
                - Is concise but complete
                - Does not sound robotic
                """
                },
                {"role": "user", "content": email_content}
            ]
            )
            content = response.choices[0].message.content
            return content.strip() if content else "No response generated."

        except Exception as e:
            return "Error generating reply."
        
    def summarize(self, email_content):
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize the email in one clear and concise sentence capturing the main intent."
                    },
                    {
                        "role": "user",
                        "content": email_content
                    }
                ]
            )
            content = response.choices[0].message.content
            return content.strip() if content else "No response generated."

        except Exception as e:
            print("SUMMARY ERROR:", e)
            return "Could not generate summary."