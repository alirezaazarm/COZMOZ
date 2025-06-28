from .openai_service import OpenAIService
from .instagram_service import InstagramService, APP_SETTINGS
from .message_service import MessageService
from ..models.enums import UserStatus, MessageRole
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Mediator:
    def __init__(self, db):
        self.db = db
        self.openai_service = OpenAIService()
        self.message_service = MessageService(db)

    def process_pending_messages(self, cutoff_time=None):
        logger.info("Starting message processing cycle")

        # Check if assistant is disabled in app settings
        if not APP_SETTINGS.get('assistant', True):
            logger.info("Assistant is disabled in app settings. Skipping message processing.")
            return

        # Get all users with WAITING status that have messages
        users_waiting = self._get_waiting_users(cutoff_time)
        logger.info(f"Found {len(users_waiting)} users with WAITING status")

        for user_id in users_waiting:
            try:
                # Process each user's messages
                self._process_user_messages(user_id, cutoff_time)
            except Exception as user_error:
                logger.error(f"Failed processing user {user_id}: {str(user_error)}", exc_info=True)
                # Update user status to indicate failure
                self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
                continue

    def _get_waiting_users(self, cutoff_time=None):
        logger.info(f"Getting users with WAITING status and messages older than {cutoff_time}")

        # Make sure cutoff_time is timezone-aware if it's not None
        if cutoff_time is not None and cutoff_time.tzinfo is None:
            cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

        # Build the match condition - only status check
        match_condition = {"status": UserStatus.WAITING.value}

        # Add additional match condition if cutoff_time is provided
        # Find users whose LATEST message is older than the cutoff time
        if cutoff_time is not None:
            # Add aggregate pipeline to find users with messages older than cutoff
            pipeline = [
                # Match users with WAITING status
                {"$match": {"status": UserStatus.WAITING.value}},

                # Find users with at least one message
                {"$match": {"direct_messages": {"$exists": True, "$ne": []}}},

                # Unwind the direct_messages array
                {"$unwind": "$direct_messages"},

                # Only consider user messages
                {"$match": {"direct_messages.role": MessageRole.USER.value}},

                # Group by user_id and find the max timestamp of user messages
                {"$group": {
                    "_id": "$user_id",
                    "latest_msg_time": {"$max": "$direct_messages.timestamp"},
                    "user_id": {"$first": "$user_id"}
                }},

                # Only include users whose latest message is older than cutoff_time
                {"$match": {"latest_msg_time": {"$lte": cutoff_time}}},

                # Only return the user_id
                {"$project": {"user_id": 1, "_id": 0}}
            ]
        else:
            # If no cutoff_time, just get all waiting users
            pipeline = [
                {"$match": match_condition},
                {"$project": {"user_id": 1, "_id": 0}}
            ]

        users = list(self.db.users.aggregate(pipeline))
        user_ids = [user.get('user_id') for user in users]

        logger.info(f"Found {len(user_ids)} users with WAITING status and latest message older than cutoff")
        return user_ids

    def _process_user_messages(self, user_id, cutoff_time=None):
        logger.info(f"Processing batch messages for user {user_id}")

        try:
            # Get user
            user = self.db.users.find_one({"user_id": user_id})
            if not user:
                logger.warning(f"User {user_id} not found")
                return

            # Ensure cutoff_time is properly timezone-aware if provided (for logging only)
            if cutoff_time is not None and cutoff_time.tzinfo is None:
                cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

            # Get all user messages since the last assistant/admin reply as a single batch
            # We don't do any filtering by timestamp here - that was done in _get_waiting_users
            user_messages = self.message_service.get_user_messages(user_id, cutoff_time)
            if not user_messages:
                logger.info(f"No user messages found for user {user_id}")
                return

            # Get the message texts for processing
            message_texts = [msg.get('text') for msg in user_messages]
            logger.info(f"Processing batch of {len(user_messages)} user messages: {message_texts}")

            # Process with OpenAI
            thread_id = self.openai_service.ensure_thread(user)
            response_text = self.openai_service.process_messages(
                thread_id,
                message_texts
            )

            if not response_text:
                logger.warning(f"No response generated for user {user_id}")
                self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
                return

            logger.info(f"Generated response: {response_text}")

            # Try to send to Instagram
            try:
                mids = InstagramService.send_message(user_id, response_text)

                # Update user status based on Instagram success and store message with MID
                if mids:
                    # Store the assistant response with MID(s) only after successful Instagram send
                    if isinstance(mids, list):
                        # Multiple messages were sent
                        for i, mid in enumerate(mids):
                            if i == 0:
                                # First message gets the full response text
                                message_doc = {
                                    "text": response_text,
                                    "role": MessageRole.ASSISTANT.value,
                                    "timestamp": datetime.now(timezone.utc),
                                    "mid": mid
                                }
                            else:
                                # Subsequent messages get part indicators
                                message_doc = {
                                    "text": f"[Part {i+1} of assistant response]",
                                    "role": MessageRole.ASSISTANT.value,
                                    "timestamp": datetime.now(timezone.utc),
                                    "mid": mid
                                }
                            
                            # Add each message part to user's direct_messages
                            self.db.users.update_one(
                                {"user_id": user_id},
                                {"$push": {"direct_messages": message_doc}}
                            )
                    else:
                        # Single message was sent
                        message_doc = {
                            "text": response_text,
                            "role": MessageRole.ASSISTANT.value,
                            "timestamp": datetime.now(timezone.utc),
                            "mid": mids
                        }
                        
                        # Add message to user's direct_messages
                        self.db.users.update_one(
                            {"user_id": user_id},
                            {"$push": {"direct_messages": message_doc}}
                        )
                    
                    # Update status to ASSISTANT_REPLIED
                    self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_REPLIED.value)
                    logger.info(f"Successfully sent and stored assistant response for user {user_id}")
                else:
                    self.message_service.update_user_status(user_id, UserStatus.INSTAGRAM_FAILED.value)

            except Exception as insta_error:
                logger.error(f"Instagram update failed: {str(insta_error)}")
                self.message_service.update_user_status(user_id, UserStatus.INSTAGRAM_FAILED.value)
                raise

        except Exception as e:
            logger.error(f"Processing failed for user {user_id}: {str(e)}", exc_info=True)
            self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
            raise
            raise