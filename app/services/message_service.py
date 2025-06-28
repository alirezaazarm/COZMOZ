from ..models.enums import UserStatus, MessageRole
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MessageService:
    def __init__(self, db):
        self.db = db

    def get_user_messages(self, user_id, cutoff_time=None):
        """
        Get all user messages since the last assistant/admin message as a single batch.

        Args:
            user_id: The user ID to get messages for
            cutoff_time: This is used to log information only, not for filtering messages

        Returns:
            List of user messages since the last assistant/admin message
        """
        logger.info(f"Getting batch messages for user {user_id}")
        try:
            # Find user and get their direct messages
            user = self.db.users.find_one(
                {"user_id": user_id, "status": UserStatus.WAITING.value},
                {"direct_messages": 1}
            )

            if not user or "direct_messages" not in user:
                logger.info(f"No user found or no messages for user {user_id}")
                return []

            # Get all messages and ensure they're sorted by timestamp
            all_messages = user.get("direct_messages", [])

            # Convert datetime objects to be timezone-aware
            for msg in all_messages:
                if "timestamp" in msg and msg["timestamp"].tzinfo is None:
                    msg["timestamp"] = msg["timestamp"].replace(tzinfo=timezone.utc)

            # Sort all messages by timestamp
            all_messages.sort(key=lambda x: x.get("timestamp", datetime.min))

            # Find the index of the last assistant or admin message
            last_non_user_idx = -1
            for i, msg in enumerate(all_messages):
                role = msg.get("role")
                if role in [MessageRole.ASSISTANT.value, MessageRole.ADMIN.value]:
                    last_non_user_idx = i

            # Get messages after the last assistant/admin message (or all if none found)
            start_idx = last_non_user_idx + 1
            recent_messages = all_messages[start_idx:]

            # Filter to only include user messages (no timestamp filtering)
            user_messages = [msg for msg in recent_messages if msg.get("role") == MessageRole.USER.value]

            message_count = len(user_messages)

            if message_count:
                logger.info(f"Found {message_count} user messages since last assistant/admin reply for user {user_id}")

                # For debugging, check if any messages are newer than cutoff_time
                if cutoff_time is not None:
                    if cutoff_time.tzinfo is None:
                        cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

                    newer_messages = sum(1 for msg in user_messages
                                       if msg.get("timestamp") > cutoff_time)

                    if newer_messages > 0:
                        logger.debug(f"{newer_messages} messages are newer than cutoff time, but including in batch anyway")

                return user_messages
            else:
                logger.info(f"No user messages since last assistant/admin reply for user {user_id}")
                return []

        except Exception as e:
            logger.error(f"Error getting messages: {str(e)}", exc_info=True)
            raise

    def _normalize_timestamp(self, timestamp):
        """Ensure timestamp is timezone-aware."""
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp

    def update_user_status(self, user_id, status):
        logger.info(f"Updating user {user_id} status to {status}")
        try:
            result = self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
            )

            success = result.modified_count > 0
            if success:
                logger.info(f"Updated user {user_id} status to {status}")
            else:
                logger.warning(f"Failed to update user {user_id} status")

            return success
        except Exception as e:
            logger.error(f"Error updating user status: {str(e)}", exc_info=True)
            return False

    # Removed save_assistant_response method - now handled directly in mediator with MID tracking

    def handle_processing_failure(self, user_id, error):
        """Handle failures in processing messages."""
        logger.error(f"Processing failed for user {user_id}: {str(error)}")

        # Update user status to indicate failure
        status = UserStatus.ASSISTANT_FAILED.value

        try:
            self.update_user_status(user_id, status)
            logger.info(f"Updated user {user_id} status to {status} due to failure")
            return True
        except Exception as e:
            logger.error(f"Failed to update user status after failure: {str(e)}")
            return False