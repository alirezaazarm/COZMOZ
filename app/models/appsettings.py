from .database import db, APP_SETTINGS_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

# In-memory store for app settings
_settings_store = {}

class AppSettings:
    """App settings model for MongoDB with in-memory caching"""
    
    @staticmethod
    def create_app_setting_document(key, value):
        """Create a new app setting document structure"""
        return {
            "key": key,
            "value": value
        }
    
    @staticmethod
    @with_db
    def get_by_key(key):
        """Get a setting by key from the database"""
        return db[APP_SETTINGS_COLLECTION].find_one({"key": key})
    
    @staticmethod
    def get_from_memory(key):
        """Get setting value from memory store"""
        return _settings_store.get(key)
    
    @staticmethod
    def get_all_from_memory():
        """Get all settings from memory store"""
        return _settings_store.copy()
    
    @staticmethod
    @with_db
    def create_or_update(key, value):
        """Create or update a setting"""
        try:
            # Upsert the setting
            result = db[APP_SETTINGS_COLLECTION].update_one(
                {"key": key},
                {"$set": {"value": value}},
                upsert=True
            )
            
            # Update in-memory store
            _update_memory_store(key, value)
            
            return result.acknowledged
        except PyMongoError as e:
            logger.error(f"Failed to create/update app setting: {str(e)}")
            return False
    
    @staticmethod
    @with_db
    def delete(key):
        """Delete a setting"""
        try:
            result = db[APP_SETTINGS_COLLECTION].delete_one({"key": key})
            
            # Remove from in-memory store
            _settings_store.pop(key, None)
            logger.info(f"Removed app setting from memory: {key}")
            
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete app setting: {str(e)}")
            return False
    
    @staticmethod
    @with_db
    def get_all():
        """Get all settings from the database"""
        return list(db[APP_SETTINGS_COLLECTION].find())

def _update_memory_store(key, value):
    """Update the in-memory store with a setting"""
    _settings_store[key] = value
    logger.info(f"Updated app setting in memory: {key}")

@with_db
def load_all_settings():
    """Load all settings into memory"""
    settings = db[APP_SETTINGS_COLLECTION].find()
    count = 0
    
    for setting in settings:
        _update_memory_store(setting["key"], setting["value"])
        count += 1
        
    logger.info(f"Loaded {count} app settings into memory") 