from enum import Enum

class MessageDirection(Enum):
    """Enumeration for message direction."""
    INCOMING = "incoming"
    OUTGOING = "outgoing"

class MessageStatus(Enum):
# =================== PHASE 1 ============================
    PENDING = "pending"                                     # just received from webhook
# =================== PHASE 2 ============================
    ASSISTANT_RESPONDED = "assistant_responded"                # but have not sent to instagram yet
    ASSISTANT_FAILED = "assist_failed_to_respond"           # assist timout
# =================== PHASE 3 ============================
    INSTAGRAM_FAILED = "failed_to_reply_instagram"          # still needs to send assist reponse to instagram
# =================== PHASE 4 ============================
    REPLIED_BY_ASSIST = "replied_by_assist"                 # completed
    REPLIED_BY_ADMIN = "replied_by_admin"                   # completed

