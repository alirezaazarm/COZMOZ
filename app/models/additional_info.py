from .database import db, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId

logger = logging.getLogger(__name__)

# Define the collection constant
ADDITIONAL_INFO_COLLECTION = 'additional_info'

class Additionalinfo:
    """Additionalinfo model for MongoDB"""

    @staticmethod
    def create_additional_text_document(title, content, file_id=None):
        """Create a new additional text document structure."""
        return {
            "title": title,
            "content": content,
            "file_id": file_id
        }

    @staticmethod
    @with_db
    def create(title, content, file_id=None):
        """Create a new additional text entry."""
        text_doc = Additionalinfo.create_additional_text_document(title, content, file_id)
        try:
            result = db[ADDITIONAL_INFO_COLLECTION].insert_one(text_doc)
            if result.acknowledged:
                text_doc["_id"] = result.inserted_id
                return text_doc
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create additional text: {str(e)}")
            return None

    @staticmethod
    @with_db
    def update(text_id, update_data):
        """Update an additional text entry by its MongoDB _id."""
        try:
            result = db[ADDITIONAL_INFO_COLLECTION].update_one(
                {"_id": ObjectId(text_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update additional text: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_by_id(text_id):
        """Get an additional text entry by its MongoDB _id."""
        try:
            return db[ADDITIONAL_INFO_COLLECTION].find_one({"_id": ObjectId(text_id)})
        except PyMongoError as e:
            logger.error(f"Failed to retrieve additional text: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete(text_id):
        """Delete an additional text entry by its MongoDB _id."""
        try:
            result = db[ADDITIONAL_INFO_COLLECTION].delete_one({"_id": ObjectId(text_id)})
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete additional text: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all():
        """Get all additional text entries."""
        try:
            return list(db[ADDITIONAL_INFO_COLLECTION].find())
        except PyMongoError as e:
            logger.error(f"Failed to retrieve additional text entries: {str(e)}")
            return []

    @staticmethod
    @with_db
    def search(search_term):
        """Search additional text entries by title or content."""
        query = {
            "$or": [
                {"title": {"$regex": search_term, "$options": "i"}},
                {"content": {"$regex": search_term, "$options": "i"}}
            ]
        }
        try:
            return list(db[ADDITIONAL_INFO_COLLECTION].find(query))
        except PyMongoError as e:
            logger.error(f"Failed to search additional text entries: {str(e)}")
            return []

    @staticmethod
    @with_db
    def get_with_file_ids():
        """Get all additional text entries that have file_ids."""
        try:
            return list(db[ADDITIONAL_INFO_COLLECTION].find({"file_id": {"$exists": True, "$ne": None}}))
        except PyMongoError as e:
            logger.error(f"Failed to retrieve additional text entries with file_ids: {str(e)}")
            return []