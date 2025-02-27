from .openai_service import OpenAIService
from .instagram_service import InstagramService
from .message_service import MessageService
from ..models.user import User
from ..models.message import DirectMessage, AssistantResponse
from ..models.enums import MessageStatus
from ..utils.helpers import handle_instagram_outcome, handle_batch_error
from ..utils.exceptions import PermanentError, RetryableError
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

class Mediator:
    def __init__(self, db):
        self.db = db
        self.openai_service = OpenAIService()
        self.message_service = MessageService(db)

    def process_pending_messages(self, cutoff_time=None):
        logger.info("Starting message processing cycle")
        users_with_pending_messages = self._get_users_with_pending_messages(cutoff_time)
        logger.info(f"Found {len(users_with_pending_messages)} users with pending messages")

        for sender_id in users_with_pending_messages:
            try:
                self._process_user_batch(sender_id, cutoff_time)
            except Exception as user_error:
                logger.error(f"Failed processing user {sender_id}: {str(user_error)}", exc_info=True)
                continue

    def _get_users_with_pending_messages(self, cutoff_time=None):
        query = (
            select(DirectMessage.sender_id)
            .where(DirectMessage.status == MessageStatus.PENDING)
        )
        if cutoff_time:
            query = query.where(DirectMessage.timestamp >= cutoff_time)
        return self.db.scalars(query.group_by(DirectMessage.sender_id).distinct()).all()

    def _process_user_batch(self, sender_id, cutoff_time=None):
        try:
            logger.info(f"Processing batch for user {sender_id}")
            with self.db.begin_nested():
                user = self.db.get(User, sender_id)
                if not user:
                    logger.warning(f"User {sender_id} not found")
                    return

                messages = self.message_service.lock_and_get_messages(sender_id, cutoff_time)
                if not messages:
                    logger.info(f"No messages found for user {sender_id}")
                    return

                message_texts = [msg.message_text for msg in messages]
                logger.debug(f"Processing {len(messages)} messages with texts: {message_texts}")

                thread_id = self.openai_service.ensure_thread(user)

                self.openai_service.wait_for_active_run_completion(thread_id)

                response_text = self.openai_service.process_messages(thread_id, message_texts)

                self.message_service.update_message_statuses(messages, MessageStatus.SENT_TO_ASSISTANT.value)

                response_record = self._create_assistant_response(messages, response_text, sender_id)

                self.db.add(response_record)
                self.db.commit()

                success = InstagramService.send_message(sender_id, response_text)
                handle_instagram_outcome(self.db, messages, success)
        except RetryableError as retry_error:
            logger.warning(f"Retryable error for user {sender_id}: {str(retry_error)}")
            handle_batch_error(self.db, retry_error, messages)
            raise
        except PermanentError as permanent_error:
            logger.error(f"Permanent error for user {sender_id}: {str(permanent_error)}")
            handle_batch_error(self.db, permanent_error, messages)
        except Exception as unexpected_error:
            logger.error(f"Unexpected error for user {sender_id}: {str(unexpected_error)}", exc_info=True)
            handle_batch_error(self.db, unexpected_error, messages)

    def _create_assistant_response(self, messages, response_text, sender_id):
        return AssistantResponse(
            message_ids=[msg.message_id for msg in messages],
            response_text=response_text,
            assistant_status=MessageStatus.ASSISTANT_RESPONDED.value,
            instagram_status=MessageStatus.PENDING.value,
            sender_id=sender_id
        )