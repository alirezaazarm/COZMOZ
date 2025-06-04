from enum import Enum

class UserStatus(Enum):
    """Enumeration for user status."""
    SCRAPED = "SCRAPED"     # User has been scraped from Instagram
    WAITING = "WAITING"   # User is waiting for a response
    REPLIED = "REPLIED"   # User has received a response
    FIXED_REPLIED = "FIXED_REPLIED"  # User has received a fixed response
    INSTAGRAM_FAILED = "INSTAGRAM_FAILED"  # Instagram failed to send the message
    ASSISTANT_FAILED = "ASSISTANT_FAILED"  # Assistant (OpenAI) failed to generate a response

class MessageRole(Enum):
    """Enumeration for message roles."""
    USER = "user"         # Message from a user
    ASSISTANT = "assistant"  # Message from the AI assistant
    ADMIN = "admin"       # Message from a human admin
    FIXED_RESPONSE = "fixed_response"  # Fixed response from the system