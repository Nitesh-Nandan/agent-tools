"""
Quick smoke test for the email configuration.
Make sure your .env has EMAIL_USERNAME and EMAIL_PASSWORD set.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import config
from src.email import sender


def main():
    if not sender.is_configured():
        print("ERROR: EMAIL_USERNAME or EMAIL_PASSWORD is not set in .env")
        sys.exit(1)

    print(f"Using email account: {config.email_username}")

    test_to = input("To address (Enter to send to self): ").strip()
    recipients = [test_to] if test_to else [config.email_username]

    success = sender.send_email(
        subject="Hello from Agent Tools MCP server",
        text_body="Test email from the SMTP tool. It works!",
        html_body="<h2>Hello from Agent Tools</h2><p>It works!</p>",
        to=recipients,
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
