from ..models.message import DirectMessage, MessageStatus
from ..services.mediator import Mediator
from ..utils.helpers import get_db
from ..config import Config
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime, UTC, timedelta
import logging

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=10))
def process_messages_job():
    logger.info("Starting message processing job")
    try:
        cutoff_time = datetime.now(UTC) - timedelta(seconds=Config.BATCH_WINDOW_SECONDS)
        with get_db() as db:
            mediator = Mediator(db)
            mediator.process_pending_messages(cutoff_time)
    except Exception as job_error:
        logger.critical(f"Job failed: {str(job_error)}", exc_info=True)
        raise
    finally:
        logger.info("Completed processing cycle")

def cleanup_processed_messages():

    with get_db() as db:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        valid_statuses = [  MessageStatus.REPLIED_BY_ASSIST.value,  MessageStatus.REPLIED_BY_ADMIN.value  ]
        db.query(DirectMessage).filter(
            DirectMessage.status.in_(valid_statuses),
            DirectMessage.timestamp < cutoff
        ).update({"status": MessageStatus.COMPLETED.value})
        db.commit()