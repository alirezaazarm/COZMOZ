from .database import db, STORIES_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Story:
    """Story model for MongoDB"""

    @staticmethod
    def create_story_document(story_id, media_type, caption, media_url, like_count=0, thumbnail_url=None, timestamp=None):
        """Create a new story document structure using an integer story_id from Meta."""
        return {
            "id": story_id,  # The unique integer from Meta
            "media_type": media_type,
            "caption": caption,
            "like_count": like_count,
            "thumbnail_url": thumbnail_url,
            "media_url" : media_url,
            "timestamp": timestamp if timestamp else datetime.now(timezone.utc)
        }

    @staticmethod
    @with_db
    def create(story_id, media_type, caption, media_url, like_count=0, thumbnail_url=None, timestamp=None):
        """Create a new story."""
        story_doc = Story.create_story_document(story_id, media_type, caption, media_url, like_count, thumbnail_url, timestamp)
        try:
            result = db[STORIES_COLLECTION].insert_one(story_doc)
            if result.acknowledged:
                story_doc["_id"] = result.inserted_id
                return story_doc
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create story: {str(e)}")
            return None

    @staticmethod
    @with_db
    def update(story_id, update_data):
        """Update a story by its MongoDB _id."""
        try:
            result = db[STORIES_COLLECTION].update_one(
                {"_id": ObjectId(story_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update story: {str(e)}")
            return False

    @staticmethod
    @with_db
    def create_or_update_from_instagram(instagram_story):
        """Create or update a story from Instagram API data"""
        existing = db[STORIES_COLLECTION].find_one({"id": instagram_story['id']})
        story_data = {
            "id": instagram_story['id'],
            "media_type": instagram_story.get('media_type', ''),
            "caption": instagram_story.get('caption', ''),
            "like_count": instagram_story.get('like_count', 0),
            "thumbnail_url": instagram_story.get('thumbnail_url', ''),
            "media_url" : instagram_story.get('media_url', ''),
            "timestamp": instagram_story.get('timestamp')
        }

        if existing:
            return db[STORIES_COLLECTION].update_one(
                {"_id": existing['_id']},
                {"$set": story_data}
            )
        else:
            return db[STORIES_COLLECTION].insert_one(story_data)

    @staticmethod
    @with_db
    def get_by_id(story_id):
        """Get a story by its MongoDB _id."""
        try:
            return db[STORIES_COLLECTION].find_one({"_id": ObjectId(story_id)})
        except PyMongoError as e:
            logger.error(f"Failed to retrieve story: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete(story_id):
        """Delete a story by its MongoDB _id."""
        try:
            result = db[STORIES_COLLECTION].delete_one({"_id": ObjectId(story_id)})
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete story: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all():
        """Get all stories."""
        try:
            return list(db[STORIES_COLLECTION].find())
        except PyMongoError as e:
            logger.error(f"Failed to retrieve stories: {str(e)}")
            return []
            
    # New fixed response methods
    FIXED_RESPONSES_COLLECTION = "fixed_responses_direct"
    
    @staticmethod
    def create_fixed_response_document(
        story_id,
        trigger_keyword,
        direct_response_text=None
    ):
        """Create a new fixed response document structure for a specific story"""
        return {
            "story_id": story_id,  # Primary identifier
            "trigger_keyword": trigger_keyword,
            "direct_response_text": direct_response_text,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    
    @staticmethod
    @with_db
    def get_fixed_response_by_id(response_id):
        """Get a fixed response by ID"""
        return db[Story.FIXED_RESPONSES_COLLECTION].find_one({"_id": ObjectId(response_id)})
    
    @staticmethod
    @with_db
    def get_fixed_response_by_story(story_id):
        """Get a fixed response for a specific story (primary query method)"""
        return db[Story.FIXED_RESPONSES_COLLECTION].find_one({"story_id": story_id})
    
    @staticmethod
    @with_db
    def get_fixed_response_by_trigger(trigger_keyword):
        """Get fixed responses by trigger keyword"""
        return list(db[Story.FIXED_RESPONSES_COLLECTION].find({"trigger_keyword": trigger_keyword}))
    
    @staticmethod
    @with_db
    def create_or_update_fixed_response(
        story_id,
        trigger_keyword,
        direct_response_text=None
    ):
        """Create or update a fixed response for a specific story"""
        # Check if a response already exists for this story
        existing = Story.get_fixed_response_by_story(story_id)
        
        if existing:
            # Update existing response
            update_data = {
                "trigger_keyword": trigger_keyword,
                "direct_response_text": direct_response_text,
                "updated_at": datetime.now(timezone.utc)
            }
            
            try:
                result = db[Story.FIXED_RESPONSES_COLLECTION].update_one(
                    {"story_id": story_id},
                    {"$set": update_data}
                )
                if result.modified_count > 0:
                    # Return the updated document
                    return Story.get_fixed_response_by_story(story_id)
                return None
            except PyMongoError as e:
                logger.error(f"Failed to update fixed response: {str(e)}")
                return None
        else:
            # Create new response
            fixed_response_doc = Story.create_fixed_response_document(
                story_id, trigger_keyword, direct_response_text
            )
            
            try:
                result = db[Story.FIXED_RESPONSES_COLLECTION].insert_one(fixed_response_doc)
                if result.acknowledged:
                    fixed_response_doc["_id"] = result.inserted_id
                    return fixed_response_doc
                return None
            except PyMongoError as e:
                logger.error(f"Failed to create fixed response: {str(e)}")
                return None
    
    @staticmethod
    @with_db
    def delete_fixed_response_by_story(story_id):
        """Delete a fixed response for a specific story"""
        try:
            result = db[Story.FIXED_RESPONSES_COLLECTION].delete_one({"story_id": story_id})
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete fixed response: {str(e)}")
            return False
    
    @staticmethod
    @with_db
    def delete_fixed_response(response_id):
        """Delete a fixed response by ID"""
        try:
            result = db[Story.FIXED_RESPONSES_COLLECTION].delete_one({"_id": ObjectId(response_id)})
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete fixed response: {str(e)}")
            return False
    
    @staticmethod
    @with_db
    def get_all_fixed_responses():
        """Get all fixed responses"""
        return list(db[Story.FIXED_RESPONSES_COLLECTION].find())