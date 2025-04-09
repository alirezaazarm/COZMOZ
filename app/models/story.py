from .database import db, STORIES_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Story:
    """Story model for MongoDB"""

    @staticmethod
    def create_story_document(story_id, media_type, caption, like_count=0, thumbnail_url=None, timestamp=None):
        """Create a new story document structure using an integer story_id from Meta."""
        return {
            "id": story_id,  # The unique integer from Meta
            "media_type": media_type,
            "caption": caption,
            "like_count": like_count,
            "thumbnail_url": thumbnail_url,
            "timestamp": timestamp if timestamp else datetime.now(timezone.utc)
        }

    @staticmethod
    @with_db
    def create(story_id, media_type, caption, like_count=0, thumbnail_url=None, timestamp=None):
        """Create a new story."""
        story_doc = Story.create_story_document(story_id, media_type, caption, like_count, thumbnail_url, timestamp)
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