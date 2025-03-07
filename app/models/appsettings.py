from sqlalchemy import Column, String, Integer, event
from .base import Base
import logging

logger = logging.getLogger(__name__)

# In-memory store for app settings
_settings_store = {}

class AppSettings(Base):
    __tablename__ = 'app_settings'
    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(String(255), nullable=False)

    @staticmethod
    def get_from_memory(key):
        """Get setting value from memory store"""
        return _settings_store.get(key)

    @staticmethod
    def get_all_from_memory():
        """Get all settings from memory store"""
        return _settings_store.copy()

def _update_memory_store(setting):
    """Update the in-memory store with a setting"""
    _settings_store[setting.key] = setting.value
    logger.info(f"Updated app setting in memory: {setting.key}")

@event.listens_for(AppSettings, 'after_insert')
def receive_after_insert(mapper, connection, target):
    """Listen for new settings"""
    _update_memory_store(target)

@event.listens_for(AppSettings, 'after_update')
def receive_after_update(mapper, connection, target):
    """Listen for setting updates"""
    _update_memory_store(target)

@event.listens_for(AppSettings, 'after_delete')
def receive_after_delete(mapper, connection, target):
    """Listen for setting deletions"""
    _settings_store.pop(target.key, None)
    logger.info(f"Removed app setting from memory: {target.key}")

def load_all_settings(session):
    """Load all settings into memory"""
    settings = session.query(AppSettings).all()
    for setting in settings:
        _update_memory_store(setting)
    logger.info(f"Loaded {len(settings)} app settings into memory")