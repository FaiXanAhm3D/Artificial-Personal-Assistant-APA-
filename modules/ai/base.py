class BaseAI:
    def generate_reply(self, email_content):
        raise NotImplementedError

    def summarize(self, email_content):
        raise NotImplementedError