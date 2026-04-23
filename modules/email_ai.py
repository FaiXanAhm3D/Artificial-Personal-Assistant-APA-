from modules.ai.selector import get_ai
import re

def clean_email_text(text):
    if not text:
        return ""

    text = re.sub(r'\s+', ' ', text)          # remove extra spaces
    text = re.sub(r'http\S+', '', text)       # remove links
    text = text.strip()

    return text[:3000]  # hard limit

ai = get_ai("groq")   # switch here anytime

def analyze_email(email_text):
    email_text = clean_email_text(email_text)
    email_lower = email_text.lower()

    prompt = f"""
    You are an assistant that classifies emails based on importance for a college student.

    Classify the email into:
    - HIGH: deadlines, assignments, exams, meetings, important notices from college (Heritage Institute of Technology, Kolkata)
    - MEDIUM: updates related to Linkedin connection and any updates which doesn't need immidiate attention.
    - LOW: promotions, ads, spam, hiring

    Email:
    {email_lower}

    Return ONLY one word: HIGH, MEDIUM, or LOW
    """

    importance = ai.generate_reply(prompt).strip().capitalize()

    try:
        summary = ai.summarize(email_text)
    except Exception as e:
        print("SUMMARY ERROR:", e)
        summary = "Could not generate summary."

    return {
        "summary": summary,
        "importance": importance
    }

def generate_reply(email_text):
    email_text = clean_email_text(email_text)
    try:
        return ai.generate_reply(email_text)
    except Exception as e:
        print("REPLY ERROR:", e)
        return None