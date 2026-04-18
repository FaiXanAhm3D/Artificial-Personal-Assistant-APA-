import os
from google import genai
from .base import BaseAI

class GeminiAI(BaseAI):
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def generate_reply(self, email_content):
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=email_content
            )
            return response.text.strip()
        except Exception as e:
            return "Could not generate reply (API issue)."