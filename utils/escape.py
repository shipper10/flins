from telegram.helpers import escape_markdown

def escape_text(text):
    return escape_markdown(str(text), version=2)
