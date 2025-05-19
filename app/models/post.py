from .database import db, POSTS_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Post:
    """Post model for MongoDB"""

    @staticmethod
    def create_post_document(post_id, caption, media_url, media_type, like_count=0, admin_explanation=None, thumbnail_url=None, timestamp=None):
        """Helper to create a new post document structure."""
        return {
            "id": post_id,  # The unique integer from Meta
            "caption": caption,
            "media_url": media_url,
            "media_type": media_type,
            "like_count": like_count,
            "thumbnail_url" : thumbnail_url,
            "timestamp": timestamp if timestamp else datetime.now(timezone.utc),
            "fixed_response": None, # Embedded directly in the post document
            "admin_explanation": admin_explanation, # Embedded
            "label": "" # Embedded
        }

    @staticmethod
    @with_db
    def create(post_id, caption, media_url, media_type, like_count=0, admin_explanation=None, thumbnail_url=None, timestamp=None):
        """Create a new post."""
        post_doc = Post.create_post_document(post_id, caption, media_url, media_type, like_count, admin_explanation, thumbnail_url, timestamp)
        try:
            result = db[POSTS_COLLECTION].insert_one(post_doc)
            if result.acknowledged:
                post_doc["_id"] = result.inserted_id
                logger.info(f"Post created with Instagram ID: {post_id}, MongoDB _id: {result.inserted_id}")
                return post_doc
            logger.warning(f"Post creation not acknowledged for Instagram ID: {post_id}")
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create post for Instagram ID {post_id}: {str(e)}")
            return None

    @staticmethod
    @with_db
    def update(instagram_post_id, update_data):
        """Update a post by its Instagram ID.
        This can be used for labels, admin_explanation, or other direct fields.
        """
        try:
            result = db[POSTS_COLLECTION].update_one(
                {"id": instagram_post_id}, # Query by Instagram ID
                {"$set": update_data}
            )
            if result.matched_count == 0:
                logger.warning(f"No post found with Instagram ID {instagram_post_id} to update.")
                return False
            logger.info(f"Post {instagram_post_id} updated. Modified count: {result.modified_count}")
            return result.modified_count > 0 # Returns True if any document was actually modified
        except PyMongoError as e:
            logger.error(f"Failed to update post {instagram_post_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def create_or_update_from_instagram(instagram_post_data):
        """Create or update a post from Instagram API data, preserving existing fixed_response, label, and admin_explanation."""
        instagram_id = instagram_post_data['id']
        existing_post = db[POSTS_COLLECTION].find_one({"id": instagram_id})

        # Data from Instagram API
        api_data = {
            "caption": instagram_post_data.get('caption', ''),
            "media_url": instagram_post_data.get('media_url', ''),
            "thumbnail_url" : instagram_post_data.get('thumbnail_url',''),
            "media_type": instagram_post_data.get('media_type', ''),
            "like_count": instagram_post_data.get('like_count', 0),
            "timestamp": instagram_post_data.get('timestamp'),
        }

        if existing_post:
            # Update existing post, but only with fields from API data
            # Fields like fixed_response, label, admin_explanation are managed separately
            # and should not be overwritten by this method unless explicitly included in instagram_post_data
            # and handled here.
            update_payload = {"$set": api_data}
            # If admin_explanation is in instagram_post_data, include it (e.g., if API provides it)
            if 'admin_explanation' in instagram_post_data: # This field is unlikely to come from API, but good practice
                update_payload["$set"]['admin_explanation'] = instagram_post_data['admin_explanation']
            if 'label' in instagram_post_data: # This field is unlikely to come from API
                 update_payload["$set"]['label'] = instagram_post_data['label']


            result = db[POSTS_COLLECTION].update_one(
                {"_id": existing_post['_id']},
                update_payload
            )
            logger.info(f"Post {instagram_id} updated from Instagram data. Modified: {result.modified_count > 0}")
            return result
        else:
            # Create new post, initializing other fields
            new_post_doc = Post.create_post_document(
                post_id=instagram_id,
                caption=api_data['caption'],
                media_url=api_data['media_url'],
                media_type=api_data['media_type'],
                like_count=api_data['like_count'],
                thumbnail_url=api_data['thumbnail_url'],
                timestamp=api_data['timestamp'],
                admin_explanation=instagram_post_data.get('admin_explanation') # if provided by API (unlikely)
            )
            # label and fixed_response are already initialized by create_post_document
            result = db[POSTS_COLLECTION].insert_one(new_post_doc)
            logger.info(f"New post {instagram_id} created from Instagram data. Inserted ID: {result.inserted_id}")
            return result

    @staticmethod
    @with_db
    def get_by_mongo_id(mongo_id):
        """Get a post by its MongoDB _id."""
        try:
            return db[POSTS_COLLECTION].find_one({"_id": ObjectId(mongo_id)})
        except PyMongoError as e:
            logger.error(f"Failed to retrieve post by MongoDB _id {mongo_id}: {str(e)}")
            return None
        except Exception: # Invalid ObjectId format
            logger.error(f"Invalid MongoDB _id format: {mongo_id}")
            return None

    @staticmethod
    @with_db
    def get_by_instagram_id(instagram_id):
        """Get a post by its Instagram ID (stored in the 'id' field)."""
        try:
            return db[POSTS_COLLECTION].find_one({"id": instagram_id})
        except PyMongoError as e:
            logger.error(f"Failed to retrieve post by Instagram ID {instagram_id}: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete_by_mongo_id(mongo_id):
        """Delete a post by its MongoDB _id."""
        try:
            result = db[POSTS_COLLECTION].delete_one({"_id": ObjectId(mongo_id)})
            logger.info(f"Post with MongoDB _id {mongo_id} deleted. Count: {result.deleted_count}")
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete post by MongoDB _id {mongo_id}: {str(e)}")
            return False
        except Exception: # Invalid ObjectId format
            logger.error(f"Invalid MongoDB _id format for deletion: {mongo_id}")
            return False

    @staticmethod
    @with_db
    def get_all():
        """Get all posts."""
        try:
            # Sort by timestamp descending (newest first)
            return list(db[POSTS_COLLECTION].find().sort("timestamp", -1))
        except PyMongoError as e:
            logger.error(f"Failed to retrieve all posts: {str(e)}")
            return []

    # --- Fixed Response Methods ---
    @staticmethod
    def _create_fixed_response_subdocument(
        trigger_keyword,
        comment_response_text=None,
        direct_response_text=None
    ):
        """Helper to create a fixed response sub-document."""
        return {
            "trigger_keyword": trigger_keyword.strip(),
            "comment_response_text": comment_response_text.strip() if comment_response_text else None,
            "direct_response_text": direct_response_text.strip() if direct_response_text else None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

    @staticmethod
    @with_db
    def set_fixed_response(
        instagram_post_id,
        trigger_keyword,
        comment_response_text=None,
        direct_response_text=None
    ):
        """Set or update the fixed response for a specific post by its Instagram ID."""
        if not trigger_keyword or not trigger_keyword.strip():
            logger.warning(f"Trigger keyword cannot be empty for post {instagram_post_id}.")
            return False

        fixed_response_subdoc = Post._create_fixed_response_subdocument(
            trigger_keyword, comment_response_text, direct_response_text
        )
        try:
            result = db[POSTS_COLLECTION].update_one(
                {"id": instagram_post_id},
                {"$set": {"fixed_response": fixed_response_subdoc}} # Overwrites existing fixed_response
            )
            if result.matched_count == 0:
                logger.warning(f"No post found with Instagram ID {instagram_post_id} to set fixed response.")
                return False
            logger.info(f"Fixed response set/updated for post {instagram_post_id}. Modified: {result.modified_count > 0}")
            # Return True if matched, even if not modified (idempotent update of same data)
            return result.matched_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to set fixed response for post {instagram_post_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_fixed_response(instagram_post_id):
        """Get the fixed response for a post by its Instagram ID."""
        post = Post.get_by_instagram_id(instagram_post_id)
        if post:
            return post.get('fixed_response') # This will be the subdocument or None
        return None

    @staticmethod
    @with_db
    def delete_fixed_response(instagram_post_id):
        """Remove (nullify) the fixed response from a post by its Instagram ID."""
        try:
            result = db[POSTS_COLLECTION].update_one(
                {"id": instagram_post_id},
                {"$set": {"fixed_response": None}} # Set the field to null
            )
            if result.matched_count == 0:
                logger.warning(f"No post found with Instagram ID {instagram_post_id} to delete fixed response.")
                return False
            logger.info(f"Fixed response deleted (set to null) for post {instagram_post_id}. Modified: {result.modified_count > 0}")
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete fixed response for post {instagram_post_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all_fixed_responses_structured():
        """
        Return all fixed responses for posts in the format:
        {
            instagram_post_id: {
                trigger: {"comment": ..., "DM": ...},
                # Only one trigger per post is supported by current embedded structure
            },
            ...
        }
        """
        posts_with_responses = db[POSTS_COLLECTION].find({"fixed_response": {"$ne": None}})
        result = {}
        for post in posts_with_responses:
            post_insta_id = post.get("id")
            fixed_resp_data = post.get("fixed_response")
            if post_insta_id and fixed_resp_data and fixed_resp_data.get("trigger_keyword"):
                trigger = fixed_resp_data["trigger_keyword"]
                comment = fixed_resp_data.get("comment_response_text")
                dm = fixed_resp_data.get("direct_response_text")
                
                # Since fixed_response is a single object, a post_id will only have one trigger.
                if post_insta_id not in result:
                    result[post_insta_id] = {}
                
                result[post_insta_id][trigger] = {"comment": comment, "DM": dm}
        return result

    # --- Label Methods ---
    @staticmethod
    @with_db
    def set_label(instagram_post_id, label):
        """Set the label for a post by its Instagram ID."""
        return Post.update(instagram_post_id, {"label": str(label).strip() if label is not None else ""})

    @staticmethod
    @with_db
    def remove_label(instagram_post_id):
        """Remove the label (set to empty string) for a post by its Instagram ID."""
        return Post.update(instagram_post_id, {"label": ""})

    @staticmethod
    @with_db
    def unset_all_labels():
        """Unset labels (set to empty string) from all posts."""
        try:
            result = db[POSTS_COLLECTION].update_many(
                {"label": {"$exists": True, "$ne": ""}}, # Only update posts that have a non-empty label
                {"$set": {"label": ""}}
            )
            logger.info(f"Unset labels for {result.modified_count} posts.")
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"Failed to unset all post labels: {str(e)}")
            return 0

    # --- Admin Explanation Methods ---
    @staticmethod
    @with_db
    def set_admin_explanation(instagram_post_id, explanation):
        """Set the admin explanation for a post by its Instagram ID."""
        return Post.update(instagram_post_id, {"admin_explanation": explanation.strip() if explanation else None})

    @staticmethod
    @with_db
    def get_admin_explanation(instagram_post_id):
        """Get the admin explanation for a post by its Instagram ID."""
        post = Post.get_by_instagram_id(instagram_post_id)
        if post:
            return post.get('admin_explanation')
        return None

    @staticmethod
    @with_db
    def remove_admin_explanation(instagram_post_id):
        """Remove (nullify) the admin explanation for a post by its Instagram ID."""
        return Post.update(instagram_post_id, {"admin_explanation": None})

