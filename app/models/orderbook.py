# NOTE: pymongo and bson are required dependencies for MongoDB models.
from .database import db, with_db
import logging
from pymongo.errors import PyMongoError  # Ensure pymongo is installed
from bson import ObjectId  # Ensure bson is installed

logger = logging.getLogger(__name__)

ORDERBOOK_COLLECTION = 'orderbook'

class Orderbook:
    """Orderbook model for MongoDB"""

    @staticmethod
    def create_orderbook_document(tx_id, status, first_name, last_name, address, phone, product, price, date, count, client_username):
        """Create a new orderbook document structure."""
        return {
            "tx_id": tx_id,
            "status": status,
            "first_name": first_name,
            "last_name": last_name,
            "address": address,
            "phone": phone,
            "product": product,
            "price": price,
            "date": date,
            "count": count,
            "client_username": client_username
        }

    @staticmethod
    @with_db
    def create(tx_id, status, first_name, last_name, address, phone, product, price, date, count, client_username):
        """Create a new orderbook entry."""
        order_doc = Orderbook.create_orderbook_document(tx_id, status, first_name, last_name, address, phone, product, price, date, count, client_username)
        try:
            if db is None:
                logger.error("Database connection is not available")
                return None
            result = db[ORDERBOOK_COLLECTION].insert_one(order_doc)
            if result.acknowledged:
                order_doc["_id"] = result.inserted_id
                return order_doc
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create orderbook entry: {str(e)}")
            return None

    @staticmethod
    @with_db
    def get_by_id(order_id):
        """Get an orderbook entry by its MongoDB _id."""
        try:
            if db is None:
                logger.error("Database connection is not available")
                return None
            return db[ORDERBOOK_COLLECTION].find_one({"_id": ObjectId(order_id)})
        except Exception as e:
            logger.error(f"Failed to retrieve orderbook entry by _id {order_id}: {str(e)}")
            return None

    @staticmethod
    @with_db
    def update(order_id, update_data):
        """Update an orderbook entry by its MongoDB _id."""
        try:
            if db is None:
                logger.error("Database connection is not available")
                return False
            result = db[ORDERBOOK_COLLECTION].update_one(
                {"_id": ObjectId(order_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update orderbook entry {order_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def delete(order_id):
        """Delete an orderbook entry by its MongoDB _id."""
        try:
            if db is None:
                logger.error("Database connection is not available")
                return False
            result = db[ORDERBOOK_COLLECTION].delete_one({"_id": ObjectId(order_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete orderbook entry {order_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all():
        """Get all orderbook entries."""
        try:
            if db is None:
                logger.error("Database connection is not available")
                return []
            return list(db[ORDERBOOK_COLLECTION].find())
        except Exception as e:
            logger.error(f"Failed to retrieve all orderbook entries: {str(e)}")
            return []

    @staticmethod
    @with_db
    def get_by_tx_id(tx_id, client_username):
        """Get an orderbook entry by its tx_id and client_username."""
        try:
            if db is None:
                logger.error("Database connection is not available")
                return None
            return db[ORDERBOOK_COLLECTION].find_one({"tx_id": tx_id, "client_username": client_username})
        except Exception as e:
            logger.error(f"Failed to retrieve orderbook entry by tx_id {tx_id}: {str(e)}")
            return None 