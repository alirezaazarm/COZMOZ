from datetime import datetime, timezone
from .database import db, FIXED_RESPONSES_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId

logger = logging.getLogger(__name__)

class FixedResponse:
    """Fixed response model for MongoDB"""
    
    @staticmethod
    def create_fixed_response_document(
        incoming, 
        trigger_keyword, 
        comment_response_text=None, 
        direct_response_text=None
    ):
        """Create a new fixed response document structure"""
        return {
            "incoming": incoming,
            "trigger_keyword": trigger_keyword,
            "comment_response_text": comment_response_text,
            "direct_response_text": direct_response_text,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    
    @staticmethod
    @with_db
    def get_by_id(response_id):
        """Get a fixed response by ID"""
        return db[FIXED_RESPONSES_COLLECTION].find_one({"_id": ObjectId(response_id)})
    
    @staticmethod
    @with_db
    def get_by_trigger(trigger_keyword):
        """Get a fixed response by trigger keyword"""
        return db[FIXED_RESPONSES_COLLECTION].find_one({"trigger_keyword": trigger_keyword})
    
    @staticmethod
    @with_db
    def create(
        incoming, 
        trigger_keyword, 
        comment_response_text=None, 
        direct_response_text=None
    ):
        """Create a new fixed response"""
        fixed_response_doc = FixedResponse.create_fixed_response_document(
            incoming, trigger_keyword, comment_response_text, direct_response_text
        )
        
        try:
            result = db[FIXED_RESPONSES_COLLECTION].insert_one(fixed_response_doc)
            if result.acknowledged:
                fixed_response_doc["_id"] = result.inserted_id
                return fixed_response_doc
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create fixed response: {str(e)}")
            return None
    
    @staticmethod
    @with_db
    def update(response_id, update_data):
        """Update a fixed response"""
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        try:
            result = db[FIXED_RESPONSES_COLLECTION].update_one(
                {"_id": ObjectId(response_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update fixed response: {str(e)}")
            return False
    
    @staticmethod
    @with_db
    def delete(response_id):
        """Delete a fixed response"""
        try:
            result = db[FIXED_RESPONSES_COLLECTION].delete_one({"_id": ObjectId(response_id)})
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete fixed response: {str(e)}")
            return False
    
    @staticmethod
    @with_db
    def get_all():
        """Get all fixed responses"""
        return list(db[FIXED_RESPONSES_COLLECTION].find())


