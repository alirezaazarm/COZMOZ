from enum import Enum

class MessageDirection(Enum):
    """Enumeration for message direction."""
    INCOMING = "incoming"
    OUTGOING = "outgoing"

class MessageStatus(Enum):
    """Enumeration for message status."""
    PENDING = "pending"
    SENT_TO_ASSISTANT = "sent_to_assist"
    ASSISTANT_RESPONDED = "assist_respond"
    ASSISTANT_FAILED = "assist_failed_to_respond"
    REPLIED_TO_INSTAGRAM = "replied_to_instagram"
    INSTAGRAM_FAILED = "failed_to_reply_instagram"
    COMPLETED = "completed"