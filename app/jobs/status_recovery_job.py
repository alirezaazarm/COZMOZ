from ..models.enums import UserStatus
from ..utils.helpers import get_db
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=10))
def recover_failed_assistant_status_job():
    """
    Job to recover users with ASSISTANT_FAILED status back to WAITING status.
    This allows them to be processed again in the next message processing cycle.
    """
    logger.info("Starting assistant status recovery job")
    try:
        with get_db() as db:
            # Find all users with ASSISTANT_FAILED status
            failed_users = list(db.users.find(
                {"status": UserStatus.ASSISTANT_FAILED.value},
                {"user_id": 1}
            ))
            
            if not failed_users:
                logger.info("No users with ASSISTANT_FAILED status found")
                return
            
            user_ids = [user["user_id"] for user in failed_users]
            logger.info(f"Found {len(user_ids)} users with ASSISTANT_FAILED status: {user_ids}")
            
            # Update all failed users back to WAITING status
            result = db.users.update_many(
                {"status": UserStatus.ASSISTANT_FAILED.value},
                {
                    "$set": {
                        "status": UserStatus.WAITING.value,
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            
            logger.info(f"Successfully updated {result.modified_count} users from ASSISTANT_FAILED to WAITING status")
            
    except Exception as job_error:
        logger.critical(f"Status recovery job failed: {str(job_error)}", exc_info=True)
        raise
    finally:
        logger.info("Completed status recovery job")