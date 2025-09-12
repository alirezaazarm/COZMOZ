from ..services.mediator import Mediator
from ..utils.helpers import get_db
from ..config import Config
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime, timezone, timedelta
import logging
from ..models.client import Client
from ..models.enums import ModuleType, Platform

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
            
            # Check if DM Assist is enabled for either platform to decide if we need a mediator
            telegram_dm_assist_enabled = client.get("platforms", {}).get("telegram", {}).get('modules', {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled", False)
            instagram_dm_assist_enabled = client.get("platforms", {}).get("instagram", {}).get('modules', {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled", False)

            if not telegram_dm_assist_enabled and not instagram_dm_assist_enabled:
                logger.info(f"DM Assist is disabled for all platforms for client '{client_username}'. Skipping.")
                continue

            with get_db() as db:
                mediator = Mediator(db, client_username=client_username)
                
                # Process Telegram messages if enabled
                if telegram_dm_assist_enabled:
                    logger.info(f"DM Assist is enabled for client '{client_username}' on Telegram. Processing pending messages.")
                    mediator.process_pending_messages(cutoff_time, platform=Platform.TELEGRAM)
                else:
                    logger.info(f"DM Assist is disabled for client '{client_username}' on Telegram. Skipping.")
                
                # Process Instagram messages if enabled
                if instagram_dm_assist_enabled:
                    logger.info(f"DM Assist is enabled for client '{client_username}' on Instagram. Processing pending messages.")
                    mediator.process_pending_messages(cutoff_time, platform=Platform.INSTAGRAM)
                else:
                    logger.info(f"DM Assist is disabled for client '{client_username}' on Instagram. Skipping.")

    except Exception as job_error:
        logger.critical(f"Job failed: {str(job_error)}", exc_info=True)
        raise
    finally:
        logger.info("Completed processing cycle")