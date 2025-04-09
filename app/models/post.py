from .database import db, POSTS_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Post:
    """Post model for MongoDB"""

    @staticmethod
    def create_post_document(post_id, caption, media_url, media_type, like_count=0, timestamp=None):
        """Create a new post document structure using an integer post_id from Meta."""
        return {
            "id": post_id,  # The unique integer from Meta
            "caption": caption,
            "media_url": media_url,
            "media_type": media_type,
            "like_count": like_count,
            "timestamp": timestamp if timestamp else datetime.now(timezone.utc)
        }

    @staticmethod
    @with_db
    def create(post_id, caption, media_url, media_type, like_count=0, timestamp=None):
        """Create a new post."""
        post_doc = Post.create_post_document(post_id, caption, media_url, media_type, like_count, timestamp)
        try:
            result = db[POSTS_COLLECTION].insert_one(post_doc)
            if result.acknowledged:
                post_doc["_id"] = result.inserted_id
                return post_doc
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create post: {str(e)}")
            return None
    @staticmethod
    @with_db
    def update(post_id, update_data):
        """Update a post by its MongoDB _id."""
        try:
            result = db[POSTS_COLLECTION].update_one(
                {"id": post_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update post: {str(e)}")
            return False

    @staticmethod
    @with_db
    def create_or_update_from_instagram(instagram_post):
        """Create or update a post from Instagram API data"""
        existing = db[POSTS_COLLECTION].find_one({"id": instagram_post['id']})
        post_data = {
            "id": instagram_post['id'],
            "caption": instagram_post.get('caption', ''),
            "media_url": instagram_post.get('media_url', ''),
            "media_type": instagram_post.get('media_type', ''),
            "like_count": instagram_post.get('like_count', 0),
            "timestamp": instagram_post.get('timestamp')
        }

        if existing:
            return db[POSTS_COLLECTION].update_one(
                {"_id": existing['_id']},
                {"$set": post_data}
            )
        else:
            return db[POSTS_COLLECTION].insert_one(post_data)
    @staticmethod
    @with_db
    def get_by_id(post_id):
        """Get a post by its MongoDB _id."""
        try:
            return db[POSTS_COLLECTION].find_one({"_id": ObjectId(post_id)})
        except PyMongoError as e:
            logger.error(f"Failed to retrieve post: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete(post_id):
        """Delete a post by its MongoDB _id."""
        try:
            result = db[POSTS_COLLECTION].delete_one({"_id": ObjectId(post_id)})
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete post: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all():
        """Get all posts."""
        try:
            return list(db[POSTS_COLLECTION].find())
        except PyMongoError as e:
            logger.error(f"Failed to retrieve posts: {str(e)}")
            return []
