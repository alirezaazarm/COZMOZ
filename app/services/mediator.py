from .openai_service import OpenAIService
from .instagram_service import InstagramService
from .message_service import MessageService
from ..models.user import User
from ..models.message import DirectMessage
from ..models.enums import MessageStatus, MessageDirection
from sqlalchemy import select
import logging
import uuid
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

class Mediator:
    def __init__(self, db):
        self.db = db
        self.openai_service = OpenAIService()
        self.message_service = MessageService(db)

    def process_pending_messages(self, cutoff_time=None):
        logger.info("Starting message processing cycle")

        # Get all users with pending messages without a transaction
        users_with_pending_messages = self._get_users_with_pending_messages(cutoff_time)
        logger.info(f"Found {len(users_with_pending_messages)} users with pending messages")

        for sender_id in users_with_pending_messages:
            try:
                # Make sure we're not in a transaction when starting a new batch
                if self.db.in_transaction():
                    self.db.commit()

                self._process_user_batch(sender_id, cutoff_time)
            except Exception as user_error:
                logger.error(f"Failed processing user {sender_id}: {str(user_error)}", exc_info=True)
                if self.db.in_transaction():
                    self.db.rollback()
                continue

    def _get_users_with_pending_messages(self, cutoff_time=None):
        logger.info(f"Getting users with pending messages since {cutoff_time}")
        query = (
            select(DirectMessage.sender_id)
            .where(
                DirectMessage.status == MessageStatus.PENDING.value,
                DirectMessage.direction == MessageDirection.INCOMING.value
            )
        )
        if cutoff_time:
            query = query.where(DirectMessage.timestamp >= cutoff_time)

        users = self.db.scalars(query.group_by(DirectMessage.sender_id).distinct()).all()
        logger.info(f"Found {len(users)} users with pending messages")

        # Log each user's ID for debugging
        if users:
            logger.debug(f"User IDs with pending messages: {users}")

        return users

    def _process_user_batch(self, sender_id, cutoff_time=None):
        messages = []
        outgoing_msg = None
        transaction_started = False

        try:
            logger.info(f"Processing batch for user {sender_id}")

            # Only start a transaction if not already in one
            if not self.db.in_transaction():
                self.db.begin()
                transaction_started = True

            # Get user first
            user = self.db.get(User, sender_id)
            if not user:
                logger.warning(f"User {sender_id} not found")
                if transaction_started:
                    self.db.commit()
                return

            # Get messages with proper locking
            messages = self.message_service.lock_and_get_messages(sender_id, cutoff_time)
            if not messages:
                logger.info(f"No messages found for user {sender_id}")
                if transaction_started:
                    self.db.commit()
                return

            message_texts = [msg.message_text for msg in messages]
            logger.info(f"Processing {len(messages)} messages with texts: {message_texts}")

            # Commit current transaction before OpenAI call
            if self.db.in_transaction():
                self.db.commit()
                transaction_started = False

            # Process with OpenAI outside of transaction
            thread_id = self.openai_service.ensure_thread(user)
            self.openai_service.wait_for_active_run_completion(thread_id)
            response_text = self.openai_service.process_messages(thread_id, message_texts)

            # Create and save response
            if not self.db.in_transaction():
                self.db.begin()
                transaction_started = True

            # Create response message
            outgoing_msg = DirectMessage(
                message_id=f"resp_{uuid.uuid4()}",
                sender_id=messages[0].recipient_id,
                recipient_id=sender_id,
                message_text=response_text,
                direction=MessageDirection.OUTGOING.value,
                status=MessageStatus.ASSISTANT_RESPONDED.value,
                response_to=[msg.message_id for msg in messages],
                timestamp=datetime.now(UTC))

            # Save response and update message statuses
            self.db.add(outgoing_msg)
            self.message_service.update_message_statuses(messages, MessageStatus.ASSISTANT_RESPONDED.value)

            if transaction_started:
                self.db.commit()
                transaction_started = False

            # Handle Instagram sending
            try:
                success = InstagramService.send_message(sender_id, response_text)

                if not self.db.in_transaction():
                    self.db.begin()
                    transaction_started = True

                new_status = (MessageStatus.REPLIED_BY_ASSIST.value if success
                            else MessageStatus.INSTAGRAM_FAILED.value)
                self.message_service.update_message_statuses(
                    messages + [outgoing_msg],
                    new_status
                )

                if transaction_started:
                    self.db.commit()
                    transaction_started = False

            except Exception as insta_error:
                logger.error(f"Instagram update failed: {str(insta_error)}")

                if not self.db.in_transaction():
                    self.db.begin()
                    transaction_started = True

                self.message_service.update_message_statuses(
                    [outgoing_msg],
                    MessageStatus.INSTAGRAM_FAILED.value
                )

                if transaction_started:
                    self.db.commit()
                    transaction_started = False
                raise

        except Exception as unexpected_error:
            logger.error(f"Processing failed: {str(unexpected_error)}")

            if self.db.in_transaction():
                self.db.rollback()
                transaction_started = False

            if messages:
                self.message_service.handle_batch_error(unexpected_error, messages)

            if outgoing_msg:
                if not self.db.in_transaction():
                    self.db.begin()
                    transaction_started = True

                self.db.delete(outgoing_msg)

                if transaction_started:
                    self.db.commit()
            raise

        finally:
            # Always make sure we don't leave transactions open
            if transaction_started and self.db.in_transaction():
                self.db.rollback()

    def _link_response_to_messages(self, messages, response_msg):
        for msg in messages:
            if not msg.response_to:
                msg.response_to = []
            msg.response_to.append(response_msg.message_id)