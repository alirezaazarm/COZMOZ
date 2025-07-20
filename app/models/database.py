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
CLIENTS_COLLECTION = 'clients'  # Collection for multi-client support (includes admins with is_admin=True)
USERS_COLLECTION = 'users'
APP_SETTINGS_COLLECTION = 'app_settings'
PRODUCTS_COLLECTION = 'products'
SCHEDULER_JOBS_COLLECTION = 'scheduler_jobs'
POSTS_COLLECTION = 'posts'
STORIES_COLLECTION = 'stories'
ADDITIONAL_TEXT_COLLECTION = 'additional_text'
# ADMIN_USERS_COLLECTION removed - admins are now stored in CLIENTS_COLLECTION with is_admin=True

def ensure_products_unique_index():
    """Ensure a unique index exists on (link, client_username) in the products collection."""
    if db is not None:
        try:
            db[PRODUCTS_COLLECTION].create_index(
                [("link", 1), ("client_username", 1)],
                unique=True,
                name="unique_link_client"
            )
            logger.info("Ensured unique index on (link, client_username) for products collection.")
        except Exception as e:
            logger.error(f"Failed to create unique index: {e}")

# Ensure the unique index is created at import time
ensure_products_unique_index()

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