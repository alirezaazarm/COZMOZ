from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from ..models.database import client, SCHEDULER_JOBS_COLLECTION
from ..config import Config
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(
    daemon=False,
    jobstores={
        'default': MongoDBJobStore(
            client=client,
            database=Config.MONGODB_DB_NAME,
            collection=SCHEDULER_JOBS_COLLECTION
        )
    },
    executors={'default': ThreadPoolExecutor(10)},
    job_defaults={'misfire_grace_time': 60, 'coalesce': True}
)

def start_scheduler():
    try:
        if not scheduler.running:
            logger.info("Starting scheduler...")
            scheduler.start()
            logger.info("Scheduler started successfully")
        else:
            logger.warning("Scheduler is already running")
    except Exception as e:
        logger.critical(f"Failed to start scheduler: {str(e)}")
        raise

def shutdown_hook():
    if scheduler.running:
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=True)
        logger.info("Scheduler shutdown complete.")
    logger.info("Closing database connections")
    # No need to dispose client - MongoDB manages connections internally