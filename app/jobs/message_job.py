from ..services.mediator import Mediator
from ..utils.helpers import get_db
from ..config import Config
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime, timezone, timedelta
import logging
from ..models.client import Client
from ..models.enums import ModuleType

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=10))
def process_messages_job():
    logger.info("Starting message processing job")
    try:
        # Get all active clients
        active_clients = Client.get_all_active()
        if not active_clients:
            logger.info("No active clients found. Skipping message processing job.")
            return

        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=Config.BATCH_WINDOW_SECONDS)
        logger.info(f"Processing messages older than {cutoff_time} (BATCH_WINDOW={Config.BATCH_WINDOW_SECONDS}s)")

        for client in active_clients:
            client_username = client.get('username')
            # Check if dm_assist module is enabled for this client
            dm_assist_enabled = client.get("modules", {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled", False)
            if not dm_assist_enabled:
                logger.info(f"DM Assist is disabled for client '{client_username}'. Skipping.")
                continue
            logger.info(f"DM Assist is enabled for client '{client_username}'. Processing pending messages.")
            with get_db() as db:
                mediator = Mediator(db, client_username=client_username)
                mediator.process_pending_messages(cutoff_time)
    except Exception as job_error:
        logger.critical(f"Job failed: {str(job_error)}", exc_info=True)
        raise
    finally:
        logger.info("Completed processing cycle")