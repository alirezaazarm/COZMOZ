from enum import Enum

class UserStatus(Enum):
    """Enumeration for user status."""
    SCRAPED = "SCRAPED"     # User has been scraped from Instagram
    WAITING = "WAITING"   # User is waiting for a response
    REPLIED = "REPLIED"   # User has received a response (deprecated - use specific types)
    ADMIN_REPLIED = "ADMIN_REPLIED"  # User has received an admin response
    ASSISTANT_REPLIED = "ASSISTANT_REPLIED"  # User has received an assistant response
    FIXED_REPLIED = "FIXED_REPLIED"  # User has received a fixed response
    INSTAGRAM_FAILED = "INSTAGRAM_FAILED"  # Instagram failed to send the message
    ASSISTANT_FAILED = "ASSISTANT_FAILED"  # Assistant (OpenAI) failed to generate a response

class MessageRole(Enum):
    """Enumeration for message roles."""
    USER = "user"         # Message from a user
    ASSISTANT = "assistant"  # Message from the AI assistant
    ADMIN = "admin"       # Message from a human admin
    FIXED_RESPONSE = "fixed_response"  # Fixed response from the system

class ClientStatus(Enum):
    """Enumeration for client status."""
    ACTIVE = "active"     # Client is active and can use the system
    INACTIVE = "inactive" # Client is temporarily inactive
    SUSPENDED = "suspended"  # Client is suspended due to policy violation
    DELETED = "deleted"   # Client has been deleted (soft delete)
    TRIAL = "trial"       # Client is on trial period
    EXPIRED = "expired"   # Client's subscription has expired

class ModuleType(Enum):
    """Enumeration for available modules."""
    INSTAGRAM_DM = "instagram_dm"           # Instagram direct messaging
    FACEBOOK_COMMENTS = "facebook_comments" # Facebook comments management
    AI_ASSISTANT = "ai_assistant"           # AI assistant functionality
    PRODUCT_CATALOG = "product_catalog"     # Product catalog management
    ANALYTICS = "analytics"                 # Analytics and reporting
    SCHEDULER = "scheduler"                 # Post scheduling
    AUTO_REPLY = "auto_reply"              # Automated replies