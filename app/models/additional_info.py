from .database import db, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
import json

logger = logging.getLogger(__name__)

# Define the collection constant
ADDITIONAL_INFO_COLLECTION = 'additional_info'

class Additionalinfo:
    """Additionalinfo model for MongoDB"""

    @staticmethod
    def create_additional_text_document(title, content, client_username, file_id=None, content_format="markdown"):
        """Create a new additional text document structure."""
        return {
            "title": title,
            "content": content,
            "content_format": content_format,  # "markdown" or "json"
            "client_username": client_username,  # Links additional info to specific client
            "file_id": file_id
        }

    @staticmethod
    @with_db
    def create(title, content, client_username, file_id=None, content_format="markdown"):
        """Create a new additional text entry."""
        text_doc = Additionalinfo.create_additional_text_document(title, content, client_username, file_id, content_format)
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
    def get_by_format(content_format, client_username=None):
        """Get all additional text entries by content format."""
        try:
            query = {"content_format": content_format}
            if client_username:
                query["client_username"] = client_username
            return list(db[ADDITIONAL_INFO_COLLECTION].find(query))
        except PyMongoError as e:
            logger.error(f"Failed to retrieve additional text entries by format: {str(e)}")
            return []

    @staticmethod
    def validate_json_content(content):
        """Validate if content is valid JSON."""
        try:
            json.loads(content)
            return True
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def parse_json_content(content):
        """Parse JSON content into key-value pairs."""
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data
            else:
                return {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def create_json_content(key_value_pairs):
        """Create JSON content from key-value pairs."""
        try:
            return json.dumps(key_value_pairs, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            return {}

    @staticmethod
    @with_db
    def update(text_id, update_data, client_username=None):
        """Update an additional text entry by its MongoDB _id."""
        try:
            query = {"_id": ObjectId(text_id)}
            if client_username:
                query["client_username"] = client_username
                
            result = db[ADDITIONAL_INFO_COLLECTION].update_one(
                query,
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update additional text: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_by_id(text_id, client_username=None):
        """Get an additional text entry by its MongoDB _id."""
        try:
            query = {"_id": ObjectId(text_id)}
            if client_username:
                query["client_username"] = client_username
            return db[ADDITIONAL_INFO_COLLECTION].find_one(query)
        except PyMongoError as e:
            logger.error(f"Failed to retrieve additional text: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete(text_id, client_username=None):
        """Delete an additional text entry by its MongoDB _id."""
        try:
            query = {"_id": ObjectId(text_id)}
            if client_username:
                query["client_username"] = client_username
                
            result = db[ADDITIONAL_INFO_COLLECTION].delete_one(query)
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete additional text: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all(client_username=None):
        """Get all additional text entries."""
        try:
            query = {}
            if client_username:
                query["client_username"] = client_username
            return list(db[ADDITIONAL_INFO_COLLECTION].find(query))
        except PyMongoError as e:
            logger.error(f"Failed to retrieve additional text entries: {str(e)}")
            return []

    @staticmethod
    @with_db
    def search(search_term, client_username=None):
        """Search additional text entries by title or content."""
        query = {
            "$or": [
                {"title": {"$regex": search_term, "$options": "i"}},
                {"content": {"$regex": search_term, "$options": "i"}}
            ]
        }
        if client_username:
            query["client_username"] = client_username
            
        try:
            return list(db[ADDITIONAL_INFO_COLLECTION].find(query))
        except PyMongoError as e:
            logger.error(f"Failed to search additional text entries: {str(e)}")
            return []

    @staticmethod
    @with_db
    def get_with_file_ids(client_username=None):
        """Get all additional text entries that have file_ids."""
        try:
            query = {"file_id": {"$exists": True, "$ne": None}}
            if client_username:
                query["client_username"] = client_username
            return list(db[ADDITIONAL_INFO_COLLECTION].find(query))
        except PyMongoError as e:
            logger.error(f"Failed to retrieve additional text entries with file_ids: {str(e)}")
            return []