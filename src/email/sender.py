"""
Email sending service using Gmail SMTP.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Optional

from src.config import config


class EmailSender:
    """A class to handle email sending via Gmail SMTP."""
    
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_name: Optional[str] = None,
    ):
        """
        Initialize EmailSender for Gmail.
        
        Args:
            username: Gmail address (from EMAIL_USERNAME env var if not provided)
            password: Gmail app password (from EMAIL_PASSWORD env var if not provided)
            from_name: Display name in From header (from EMAIL_FROM_NAME if not provided)
        """
        self.username = username or config.email_username
        self.password = password or config.email_password
        self.from_name = from_name if from_name is not None else config.email_from_name
        self.smtp_host = 'smtp.gmail.com'
        self.smtp_port = 587
    
    def send_email(
        self,
        subject: str,
        html_body: str,
        text_body: str,
        to: list[str],
        reply_to: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> bool:
        """
        Send an email with both HTML and plain text versions.
        
        Args:
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body
            to: List of recipient email addresses
            reply_to: Reply-to email address
            from_name: Optional display name for the From header
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.username or not self.password:
            print("✗ Email credentials not configured")
            return False
        
        try:
            if not to:
                print("✗ No recipients specified")
                return False
                
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = formataddr((from_name or self.from_name, self.username or ""))
            msg['To'] = ", ".join(to)
            msg['Subject'] = subject
            
            if reply_to:
                msg['Reply-To'] = reply_to
            
            # Attach both plain text and HTML versions
            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            print(f"✓ Email sent successfully to {', '.join(to)}")
            return True
            
        except Exception as e:
            print(f"✗ Failed to send email: {str(e)}")
            return False
    
    def is_configured(self) -> bool:
        """
        Check if email credentials are configured.
        
        Returns:
            True if credentials are set, False otherwise
        """
        return bool(self.username and self.password)
