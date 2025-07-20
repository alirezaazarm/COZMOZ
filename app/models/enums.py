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
    """Enumeration for available client modules."""
    FIXED_RESPONSE = "fixed_response"         # Fixed response automation
    DM_ASSIST = "dm_assist"                   # Direct message assistant
    COMMENT_ASSIST = "comment_assist"         # Comment assistant
    VISION = "vision"                         # Vision/image analysis
    SCRAPER = "scraper"                       # Web/IG scraper
    ORDERBOOK = "orderbook"                   # Orderbook management

class OrderStatus(Enum):
    """Enumeration for order status."""
    PENDING = "pending"         # Order is pending and awaiting to confirm by admin
    PREPARING = "preparing"     # Order is being prepared
    SENT = "sent"               # Order has been sent
    REJECTED = "rejected"       # Order has been rejected by admin
    REFUNDED = "refunded"       # Order has been refunded
    RETURNED = "returned"       # Order has been returned