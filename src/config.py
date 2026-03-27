"""
Environment configuration loader.
Centralises reading and typing of environment variables.
"""

import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class AppConfig(BaseModel):
    # Database Settings
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    
    # MCP Settings
    mcp_host: str
    mcp_port: int
    
    # Email Settings
    email_username: str | None
    email_password: str | None
    email_from_name: str

def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    return AppConfig(
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_name=os.environ.get("DB_NAME", "agent_memory"),
        db_user=os.environ.get("DB_USER", "postgres"),
        db_password=os.environ.get("DB_PASSWORD", ""),
        mcp_host=os.environ.get("MCP_HOST", "0.0.0.0"),
        mcp_port=int(os.environ.get("MCP_PORT", "8000")),
        email_username=os.environ.get("EMAIL_USERNAME"),
        email_password=os.environ.get("EMAIL_PASSWORD"),
        email_from_name=os.environ.get("EMAIL_FROM_NAME", "Personal Agent"),
    )

config = load_config()
