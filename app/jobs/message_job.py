from ..services.mediator import Mediator
from ..utils.helpers import get_db
from ..config import Config
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=10))
def process_messages_job():
    logger.info("Starting message processing job")
    try:

        from ..services.instagram_service import APP_SETTINGS

        # Check if assistant is disabled in app settings
        if not APP_SETTINGS.get('assistant', False):
            logger.info("Assistant is disabled in app settings. Skipping message processing job.")
            return

        logger.info("Assistant is enabled. Processing pending messages.")

        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=Config.BATCH_WINDOW_SECONDS)
        logger.info(f"Processing messages older than {cutoff_time} (BATCH_WINDOW={Config.BATCH_WINDOW_SECONDS}s)")

        with get_db() as db:
            mediator = Mediator(db)
            mediator.process_pending_messages(cutoff_time)

    except Exception as job_error:
        logger.critical(f"Job failed: {str(job_error)}", exc_info=True)
        raise
    finally:
        logger.info("Completed processing cycle")