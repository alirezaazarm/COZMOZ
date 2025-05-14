from .database import db, POSTS_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Post:
    """Post model for MongoDB"""

    @staticmethod
    def create_post_document(post_id, caption, media_url, media_type, like_count=0, thumbnail_url=None, timestamp=None):
        """Create a new post document structure using an integer post_id from Meta."""
        return {
            "id": post_id,  # The unique integer from Meta
            "caption": caption,
            "media_url": media_url,
            "media_type": media_type,
            "like_count": like_count,
            "thumbnail_url" : thumbnail_url,
            "timestamp": timestamp if timestamp else datetime.now(timezone.utc),
            "fixed_response": None  # Default field for fixed response
        }

    @staticmethod
    @with_db
    def create(post_id, caption, media_url, media_type, like_count=0, thumbnail_url=None, timestamp=None):
        """Create a new post."""
        post_doc = Post.create_post_document(post_id, caption, media_url, thumbnail_url, media_type, like_count, timestamp)
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
            "thumbnail_url" : instagram_post.get('thumbnail_url',''),
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
            post_data["fixed_response"] = None  # Initialize with no fixed response
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
    def get_by_instagram_id(instagram_id):
        """Get a post by its Instagram ID (stored in the 'id' field)."""
        try:
            return db[POSTS_COLLECTION].find_one({"id": instagram_id})
        except PyMongoError as e:
            logger.error(f"Failed to retrieve post by Instagram ID: {str(e)}")
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

    # Fixed response methods using the post collection
    @staticmethod
    def create_fixed_response_object(
        trigger_keyword, 
        comment_response_text=None, 
        direct_response_text=None
    ):
        """Create a fixed response object to be stored in the post document"""
        return {
            "trigger_keyword": trigger_keyword,
            "comment_response_text": comment_response_text,
            "direct_response_text": direct_response_text,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    
    @staticmethod
    @with_db
    def get_posts_with_fixed_responses():
        """Get all posts that have fixed responses"""
        return list(db[POSTS_COLLECTION].find({"fixed_response": {"$ne": None}}))
    
    @staticmethod
    @with_db
    def get_posts_by_trigger_keyword(trigger_keyword):
        """Get posts that have fixed responses with a specific trigger keyword"""
        return list(db[POSTS_COLLECTION].find({"fixed_response.trigger_keyword": trigger_keyword}))
    
    @staticmethod
    @with_db
    def set_fixed_response(
        post_id,
        trigger_keyword, 
        comment_response_text=None, 
        direct_response_text=None
    ):
        """Set a fixed response for a specific post"""
        fixed_response = Post.create_fixed_response_object(
            trigger_keyword, comment_response_text, direct_response_text
        )
        
        try:
            result = db[POSTS_COLLECTION].update_one(
                {"id": post_id},
                {"$set": {"fixed_response": fixed_response}}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to set fixed response: {str(e)}")
            return False
    
    @staticmethod
    @with_db
    def remove_fixed_response(post_id):
        """Remove the fixed response from a post"""
        try:
            result = db[POSTS_COLLECTION].update_one(
                {"id": post_id},
                {"$set": {"fixed_response": None}}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to remove fixed response: {str(e)}")
            return False
