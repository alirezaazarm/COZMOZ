from .AI.openai_service import OpenAIService
from .platforms.instagram import InstagramService
from .platforms.telegram import TelegramService
from .message_service import MessageService
from ..models.enums import UserStatus, MessageRole, ModuleType, Platform
from ..utils.helpers import get_app_settings
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Mediator:
    def __init__(self, db, client_username):
        self.db = db
        self.client_username = client_username
        self.openai_service = OpenAIService(client_username=client_username)
        self.message_service = MessageService(db, client_username)

    def process_pending_messages(self, cutoff_time=None, platform=None):
        platform_log = f" for platform: {platform.value}" if platform else ""
        logger.info(f"Starting message processing cycle for client: {self.client_username}{platform_log}")

        # Check if assistant is disabled in app settings (client-specific)
        app_settings = get_app_settings(self.client_username)
        if not app_settings.get(ModuleType.DM_ASSIST.value, True):
            logger.info(f"Assistant is disabled in app settings for client {self.client_username}. Skipping message processing.")
            return

        # Get all users with WAITING status that have messages (client-specific and platform-specific)
        users_waiting = self._get_waiting_users(cutoff_time, platform)
        logger.info(f"Found {len(users_waiting)} users with WAITING status for client {self.client_username}{platform_log}")

        for user_id in users_waiting:
            try:
                # Process each user's messages
                self._process_user_messages(user_id, cutoff_time)
            except Exception as user_error:
                logger.error(f"Failed processing user {user_id} for client {self.client_username}: {str(user_error)}", exc_info=True)
                # Update user status to indicate failure
                self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
                continue

    def _get_waiting_users(self, cutoff_time=None, platform=None):
        platform_log = f" and platform {platform.value}" if platform else ""
        logger.info(f"Getting users with WAITING status and messages older than {cutoff_time} for client {self.client_username}{platform_log}")

        # Make sure cutoff_time is timezone-aware if it's not None
        if cutoff_time is not None and cutoff_time.tzinfo is None:
            cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

        # Build the match condition - status and client_username
        match_condition = {"status": UserStatus.WAITING.value, "client_username": self.client_username}
        
        # Add platform to match condition if provided
        if platform:
            match_condition["platform"] = platform.value

        # Build the aggregation pipeline
        pipeline = [{"$match": match_condition}]

        # Add additional match condition if cutoff_time is provided
        # Find users whose LATEST message is older than the cutoff time
        if cutoff_time is not None:
            pipeline.extend([
                {"$match": {"direct_messages": {"$exists": True, "$ne": []}}},
                {"$unwind": "$direct_messages"},
                {"$match": {"direct_messages.role": MessageRole.USER.value}},
                {"$group": {
                    "_id": "$user_id",
                    "latest_msg_time": {"$max": "$direct_messages.timestamp"},
                    "user_id": {"$first": "$user_id"}
                }},
                {"$match": {"latest_msg_time": {"$lte": cutoff_time}}}
            ])
        
        pipeline.append({"$project": {"user_id": 1, "_id": 0}})

        users = list(self.db.users.aggregate(pipeline))
        user_ids = [user.get('user_id') for user in users]

        logger.info(f"Found {len(user_ids)} users with WAITING status and latest message older than cutoff for client {self.client_username}{platform_log}")
        return user_ids

    def _process_user_messages(self, user_id, cutoff_time=None):
        logger.info(f"Processing batch messages for user {user_id} (client: {self.client_username})")

        try:
            # Get user (client-specific)
            user = self.db.users.find_one({"user_id": user_id, "client_username": self.client_username})
            if not user:
                logger.warning(f"User {user_id} not found for client {self.client_username}")
                return

            # Ensure cutoff_time is properly timezone-aware if provided (for logging only)
            if cutoff_time is not None and cutoff_time.tzinfo is None:
                cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

            # Get all user messages since the last assistant/admin reply as a single batch
            user_messages = self.message_service.get_user_messages(user_id, cutoff_time)
            if not user_messages:
                logger.info(f"No user messages found for user {user_id} (client: {self.client_username})")
                return

            # Get the message texts for processing
            message_texts = [msg.get('text') for msg in user_messages]
            logger.info(f"Processing batch of {len(user_messages)} user messages: {message_texts} (client: {self.client_username})")

            # Process with OpenAI (client-specific)
            thread_id = self.openai_service.ensure_thread(user)
            response_text = self.openai_service.process_messages(
                thread_id,
                message_texts
            )

            if not response_text:
                logger.warning(f"No response generated for user {user_id} (client: {self.client_username})")
                self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
                return

            logger.info(f"Generated response: {response_text} (client: {self.client_username})")

            # Determine platform and send via appropriate service (client-specific)
            try:
                platform_value = user.get("platform")
                if platform_value == Platform.INSTAGRAM.value:
                    mids = InstagramService.send_message(user_id, response_text, client_username=self.client_username)

                    if mids:
                        if isinstance(mids, list):
                            for i, mid in enumerate(mids):
                                if i == 0:
                                    message_doc = {
                                        "text": response_text,
                                        "role": MessageRole.ASSISTANT.value,
                                        "timestamp": datetime.now(timezone.utc),
                                        "mid": mid
                                    }
                                else:
                                    message_doc = {
                                        "text": f"[Part {i+1} of assistant response]",
                                        "role": MessageRole.ASSISTANT.value,
                                        "timestamp": datetime.now(timezone.utc),
                                        "mid": mid
                                    }
                                self.db.users.update_one(
                                    {"user_id": user_id, "client_username": self.client_username},
                                    {"$push": {"direct_messages": message_doc}}
                                )
                        else:
                            message_doc = {
                                "text": response_text,
                                "role": MessageRole.ASSISTANT.value,
                                "timestamp": datetime.now(timezone.utc),
                                "mid": mids
                            }
                            self.db.users.update_one(
                                {"user_id": user_id, "client_username": self.client_username},
                                {"$push": {"direct_messages": message_doc}}
                            )
                        self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_REPLIED.value)
                        logger.info(f"Successfully sent and stored assistant response for IG user {user_id} (client: {self.client_username})")
                    else:
                        self.message_service.update_user_status(user_id, UserStatus.INSTAGRAM_FAILED.value)
                elif platform_value == Platform.TELEGRAM.value:
                    message_id = TelegramService.send_message(chat_id=user_id, text=response_text, client_username=self.client_username)
                    if message_id:
                        message_doc = {
                            "text": response_text,
                            "role": MessageRole.ASSISTANT.value,
                            "timestamp": datetime.now(timezone.utc),
                            "mid": message_id
                        }
                        self.db.users.update_one(
                            {"user_id": user_id, "client_username": self.client_username},
                            {"$push": {"direct_messages": message_doc}}
                        )
                        self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_REPLIED.value)
                        logger.info(f"Successfully sent and stored assistant response for TG user {user_id} (client: {self.client_username})")
                    else:
                        self.message_service.update_user_status(user_id, UserStatus.TELEGRAM_FAILED.value)
                else:
                    logger.error(f"Unknown or unsupported platform '{platform_value}' for user {user_id}")
                    self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)

            except Exception as insta_error:
                logger.error(f"Message send failed for client {self.client_username}: {str(insta_error)}")
                # Set platform-specific failure when possible
                platform_value = user.get("platform")
                if platform_value == Platform.TELEGRAM.value:
                    self.message_service.update_user_status(user_id, UserStatus.TELEGRAM_FAILED.value)
                elif platform_value == Platform.INSTAGRAM.value:
                    self.message_service.update_user_status(user_id, UserStatus.INSTAGRAM_FAILED.value)
                else:
                    self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
                raise

        except Exception as e:
            logger.error(f"Processing failed for user {user_id} (client: {self.client_username}): {str(e)}", exc_info=True)
            self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
            raise