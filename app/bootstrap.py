"""Controlled initial administrator provisioning for an empty deployment."""

import logging

from .config import Config
from .models.client import Client
from .models.database import CLIENTS_COLLECTION, db

logger = logging.getLogger(__name__)


def ensure_initial_system_admin() -> None:
    if db is None or db[CLIENTS_COLLECTION].count_documents({"is_admin": True}, limit=1):
        return
    username = Config.INITIAL_SYSTEM_ADMIN_USERNAME
    password = Config.INITIAL_SYSTEM_ADMIN_PASSWORD
    if not username or not password:
        logger.critical("No administrator exists. Set INITIAL_SYSTEM_ADMIN_USERNAME and INITIAL_SYSTEM_ADMIN_PASSWORD.")
        return
    if len(password) < 12:
        logger.critical("INITIAL_SYSTEM_ADMIN_PASSWORD must contain at least 12 characters.")
        return
    account = Client.create_admin(username, password, business_name="System administration")
    if account:
        db[CLIENTS_COLLECTION].update_one({"username": username}, {"$set": {"role": "system_admin"}})
        logger.warning("Created the configured initial system administrator. Remove INITIAL_SYSTEM_ADMIN_PASSWORD after first start.")
