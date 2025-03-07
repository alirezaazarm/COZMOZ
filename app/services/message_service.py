from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models.message import DirectMessage
from ..models.enums import MessageStatus, MessageDirection
from ..utils.exceptions import PermanentError
import logging

logger = logging.getLogger(__name__)

class MessageService:
    def __init__(self, db: Session):
        self.db = db

    def lock_and_get_messages(self, sender_id, cutoff_time):
        logger.info(f"Locking messages for user {sender_id}")
        try:
            self.db.expire_all()
            
            # Execute the query directly if already in a transaction
            query = (
                select(DirectMessage)
                .where(
                    DirectMessage.sender_id == sender_id,
                    DirectMessage.status == MessageStatus.PENDING,
                    DirectMessage.direction == MessageDirection.INCOMING
                )
                .with_for_update(skip_locked=True)
                .order_by(DirectMessage.timestamp)
            )
            
            # Use cutoff_time if provided
            if cutoff_time:
                query = query.where(DirectMessage.timestamp >= cutoff_time)
            
            messages = self.db.execute(query).scalars().all()
            message_count = len(messages)
            
            if message_count:
                logger.info(f"Locked {message_count} pending messages for user {sender_id}")
                message_ids = [msg.message_id for msg in messages]
                logger.debug(f"Message IDs: {message_ids}")
            else:
                logger.info(f"No pending messages found for user {sender_id}")
                
            return messages
        except Exception as e:
            logger.error(f"Locking failed: {str(e)}")
            raise

    def update_message_statuses(self, messages, status):
        try:
            for msg in messages:
                msg.status = status
            self.db.flush()
        except Exception as e:
            logger.error(f"Status update failed: {str(e)}")
            raise

    def get_pending_users_query(self, cutoff_time):
        logger.info(f"Constructing query to retrieve pending users with cutoff_time: {cutoff_time}")
        try:
            query = (
                select(DirectMessage.sender_id)
                .where(
                    DirectMessage.status == MessageStatus.PENDING,
                    DirectMessage.timestamp >= cutoff_time
                )
                .group_by(DirectMessage.sender_id)
                .distinct()
            )
            logger.debug(f"Query constructed: {query}")
            return query
        except Exception as e:
            logger.error(f"Error while constructing query for pending users: {str(e)}")
            raise

    def handle_batch_error(self, error, messages):
        try:
            if not messages:
                logger.warning("No messages to handle in batch error")
                return

            new_status = MessageStatus.PENDING.value
            if isinstance(error, PermanentError):
                new_status = MessageStatus.ASSISTANT_FAILED.value

            valid_statuses = [e.value for e in MessageStatus]
            if new_status not in valid_statuses:
                raise ValueError(f"Invalid status {new_status}")

            message_ids = [msg.message_id for msg in messages]

            # Check if we need to start a transaction
            transaction_started = False
            if not self.db.in_transaction():
                self.db.begin()
                transaction_started = True

            # Update message statuses
            self.db.query(DirectMessage).filter(
                DirectMessage.message_id.in_(message_ids)
            ).update({"status": new_status}, synchronize_session=False)

            self.db.query(DirectMessage).filter(
                DirectMessage.response_to.contains(message_ids)
            ).update(
                {"status": MessageStatus.ASSISTANT_FAILED.value},
                synchronize_session=False
            )

            # Only commit if we started the transaction
            if transaction_started:
                self.db.commit()

        except Exception as e:
            logger.critical(f"Batch error handling failed: {str(e)}")
            if self.db.in_transaction():
                self.db.rollback()
            raise