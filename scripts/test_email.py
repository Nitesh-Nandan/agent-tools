"""
Simple script to test the email sending configuration.
Make sure your .env has EMAIL_USERNAME and EMAIL_PASSWORD exported.
"""

import sys
import os

# Ensure the root directory is in sys.path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import config
from src.email.sender import EmailSender

def main():
    if not config.email_username or not config.email_password:
        print("❌ Error: EMAIL_USERNAME or EMAIL_PASSWORD is not set in your config (.env file).")
        sys.exit(1)

    print(f"📧 Using email account: {config.email_username}")
    
    sender = EmailSender()
    
    if not sender.is_configured():
        print("❌ Error: sender.is_configured() returned false. Check your configuration.")
        sys.exit(1)

    # Prompt user for destination email, fallback to a default if they provided one in code
    test_to = input("To address (press Enter to send to the authenticated user): ").strip()
    recipients = [test_to] if test_to else [config.email_username]

    subject = "Hello from Agent Tools MCP server"
    text_body = "This is a test email sent from the newly configured SMTP email tool.\n\nIt works!"
    html_body = """
    <h2>Hello from Agent Tools MCP server</h2>
    <p>This is a <strong>test email</strong> sent from the newly configured SMTP email tool.</p>
    <p>It works! 🎉</p>
    """

    print(f"Submitting email to {recipients}...")
    success = sender.send_email(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        to=recipients
    )

    if success:
        print("✅ Email sent successfully!")
    else:
        print("❌ Failed to send email. Check the application logs for SMTP tracebacks.")
        sys.exit(1)

if __name__ == "__main__":
    main()
