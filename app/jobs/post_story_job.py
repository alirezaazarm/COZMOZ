import logging
import time
from tenacity import retry, stop_after_attempt, wait_exponential
from ..services.instagram_service import InstagramService
from ..utils.helpers import get_db

# Set up logging
logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=10))
def fetch_posts_job():
    logger.info("Starting Instagram post fetch job")
    try:
        start_time = time.time()

        with get_db() as db:
            success = InstagramService.get_posts()

            elapsed_time = time.time() - start_time
            if success:
                logger.info(f"Successfully fetched Instagram posts in {elapsed_time:.2f} seconds")
            else:
                logger.error(f"Failed to fetch Instagram posts after {elapsed_time:.2f} seconds")

            return success

    except Exception as job_error:
        logger.critical(f"Post fetch job failed: {str(job_error)}", exc_info=True)
        raise
    finally:
        logger.info("Completed Instagram post fetch cycle")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=10))
def fetch_stories_job():
    logger.info("Starting Instagram story fetch job")
    try:
        start_time = time.time()
        with get_db() as db:
            success = InstagramService.get_stories()

            elapsed_time = time.time() - start_time
            if success:
                logger.info(f"Successfully fetched Instagram stories in {elapsed_time:.2f} seconds")
            else:
                logger.error(f"Failed to fetch Instagram stories after {elapsed_time:.2f} seconds")

            return success

    except Exception as job_error:
        logger.critical(f"Story fetch job failed: {str(job_error)}", exc_info=True)
        raise
    finally:
        logger.info("Completed Instagram story fetch cycle")