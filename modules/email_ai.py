from modules.ai.selector import get_ai

ai = get_ai("groq")   # 🔥 switch here anytime

def analyze_email(email_text):
    email_lower = email_text.lower()

    if any(word in email_lower for word in ["urgent", "deadline", "important", "exam", "interview"]):
        importance = "High"
    elif any(word in email_lower for word in ["sale", "offer", "discount", "promotion"]):
        importance = "Low"
    else:
        importance = "Medium"

    summary = ai.summarize(email_text)

    if importance == "Low" or importance == "Medium":
        reply = "No reply needed."
    else:
        reply = ai.generate_reply(email_text)

    return {
        "summary": summary,
        "importance": importance,
        "reply": reply
    }