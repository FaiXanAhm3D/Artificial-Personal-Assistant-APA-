from .groq_ai import GroqAI
from .gemini_ai import GeminiAI

def get_ai(model="groq"):
    if model == "groq":
        return GroqAI()
    elif model == "gemini":
        return GeminiAI()
    else:
        raise ValueError("Invalid AI model")