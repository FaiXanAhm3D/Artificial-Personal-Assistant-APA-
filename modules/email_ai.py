def analyze_email(email_text):
    email_lower = email_text.lower()

    if any(word in email_lower for word in ["urgent", "deadline", "important", "exam", "interview"]):
        importance = "High"
    elif any(word in email_lower for word in ["sale", "offer", "discount", "promotion"]):
        importance = "Low"
    else:
        importance = "Medium"

    summary = email_text.strip().split("\n")[0][:150]

    reply = generate_reply(email_text, importance)

    return {
        "summary": summary,
        "importance": importance,
        "reply": reply
    }


def generate_reply(email_text, importance):
    if importance == "High":
        return "Thank you for your email. I have noted the details and will respond promptly."

    elif importance == "Medium":
        return "Thank you for reaching out. I will review this and get back to you shortly."

    else:
        return "Thank you for the information."