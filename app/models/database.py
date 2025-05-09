from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from ..config import Config
import logging
from functools import wraps

logger = logging.getLogger(__name__)

# MongoDB client instance
try:
    client = MongoClient(Config.MONGODB_URI)
    # Ping the server to verify connection
    client.admin.command('ping')
    logger.info("Successfully connected to MongoDB")
except ConnectionFailure as e:
    logger.critical(f"Failed to connect to MongoDB: {str(e)}")
    client = None

# Database instance
db = client[Config.MONGODB_DB_NAME] if client else None

# Collection constants - only keeping collections that are still needed
USERS_COLLECTION = 'users'
FIXED_RESPONSES_COLLECTION = 'fixed_responses'
APP_SETTINGS_COLLECTION = 'app_settings'
PRODUCTS_COLLECTION = 'products'
SCHEDULER_JOBS_COLLECTION = 'scheduler_jobs'
POSTS_COLLECTION = 'posts'
STORIES_COLLECTION = 'stories'
ADDITIONAL_TEXT_COLLECTION = 'additional_text'

# Context manager for database operations
def with_db(func):
    """Decorator to provide database connection to functions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if db is None:
            logger.error("Database connection is not available")
            return None
        return func(*args, **kwargs)
    return wrapper