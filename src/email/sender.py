"""
Email sending via Gmail SMTP.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from src.config import config


def is_configured() -> bool:
    return bool(config.email_username and config.email_password)


def send_email(
    subject: str,
    html_body: str,
    text_body: str,
    to: list[str],
    from_name: str,
    reply_to: str | None = None,
) -> bool:
    if not config.email_username or not config.email_password:
        print("✗ Email credentials not configured")
        return False
    if not to:
        print("✗ No recipients specified")
        return False

    try:
        msg = MIMEMultipart("alternative")
        display_name = from_name
        msg["From"] = formataddr((display_name, config.email_username))
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(config.email_username, config.email_password)
            server.send_message(msg)

        print(f"✓ Email sent to {', '.join(to)}")
        return True
    except Exception as e:
        print(f"✗ Failed to send email: {e}")
        return False
