from .database import db, POSTS_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Post:
    """Post model for MongoDB"""

    @staticmethod
    def create_post_document(post_id, caption, media_url, media_type, client_username, like_count=0, admin_explanation=None, thumbnail_url=None, timestamp=None, children=None):
        """Helper to create a new post document structure."""
        return {
            "id": post_id,  # The unique integer from Meta
            "caption": caption,
            "media_url": media_url,
            "media_type": media_type,
            "client_username": client_username,  # Links post to specific client
            "like_count": like_count,
            "thumbnail_url" : thumbnail_url,
            "timestamp": timestamp if timestamp else datetime.now(timezone.utc),
            "children": children if children else [],  # Array to store children media
            "fixed_responses": [], # Changed to an array to support multiple fixed responses
            "admin_explanation": admin_explanation, # Embedded
            "label": "" # Embedded
        }

    @staticmethod
    @with_db
    def create(post_id, caption, media_url, media_type, client_username, like_count=0, admin_explanation=None, thumbnail_url=None, timestamp=None, children=None):
        """Create a new post."""
        post_doc = Post.create_post_document(post_id, caption, media_url, media_type, client_username, like_count, admin_explanation, thumbnail_url, timestamp, children)
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
    def update(instagram_post_id, update_data, client_username=None):
        """Update a post by its Instagram ID.
        This can be used for labels, admin_explanation, or other direct fields.
        """
        try:
            query = {"id": instagram_post_id}
            if client_username:
                query["client_username"] = client_username

            result = db[POSTS_COLLECTION].update_one(
                query, # Query by Instagram ID and optionally client
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
    def create_or_update_from_instagram(instagram_post_data, client_username):
        """Create or update a post from Instagram API data, preserving existing fixed_responses, label, and admin_explanation."""
        instagram_id = instagram_post_data['id']
        query = {"id": instagram_id}
        if client_username:
            query["client_username"] = client_username
        existing_post = db[POSTS_COLLECTION].find_one(query)

        # Process children data if exists
        children_data = []
        if 'children' in instagram_post_data:
            # Handle both direct API format and our internal format
            if 'data' in instagram_post_data['children']:
                # This is the format directly from the Instagram API
                for child in instagram_post_data['children']['data']:
                    child_item = {}
                    if 'media_url' in child:
                        child_item['media_url'] = child['media_url']
                    if 'thumbnail_url' in child:
                        child_item['thumbnail_url'] = child['thumbnail_url']
                    # We don't need to store the children IDs as per requirements
                    if child_item:  # Only add if we have at least one URL
                        children_data.append(child_item)

        # Data from Instagram API
        api_data = {
            "caption": instagram_post_data.get('caption', ''),
            "media_url": instagram_post_data.get('media_url', ''),
            "thumbnail_url" : instagram_post_data.get('thumbnail_url',''),
            "media_type": instagram_post_data.get('media_type', ''),
            "like_count": instagram_post_data.get('like_count', 0),
            "timestamp": instagram_post_data.get('timestamp'),
            "children": children_data,
        }

        if existing_post:
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
                client_username=client_username,
                like_count=api_data['like_count'],
                thumbnail_url=api_data['thumbnail_url'],
                timestamp=api_data['timestamp'],
                children=children_data,
                admin_explanation=instagram_post_data.get('admin_explanation') # if provided by API (unlikely)
            )
            # label and fixed_responses are already initialized by create_post_document
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
    def get_by_instagram_id(instagram_id, client_username=None):
        """Get a post by its Instagram ID (stored in the 'id' field)."""
        try:
            query = {"id": instagram_id}
            if client_username:
                query["client_username"] = client_username
            return db[POSTS_COLLECTION].find_one(query)
        except PyMongoError as e:
            logger.error(f"Failed to retrieve post by Instagram ID {instagram_id}: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete_by_mongo_id(mongo_id, client_username=None):
        """Delete a post by its MongoDB _id."""
        try:
            query = {"_id": ObjectId(mongo_id)}
            if client_username:
                query["client_username"] = client_username
            result = db[POSTS_COLLECTION].delete_one(query)
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
    def get_all(client_username=None):
        """Get all posts."""
        try:
            query = {}
            if client_username:
                query["client_username"] = client_username
            # Sort by timestamp descending (newest first)
            return list(db[POSTS_COLLECTION].find(query).sort("timestamp", -1))
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
    def add_fixed_response(
        instagram_post_id,
        trigger_keyword,
        client_username=None,
        comment_response_text=None,
        direct_response_text=None
    ):
        """
        Adds a new fixed response to a post or updates an existing one if the trigger_keyword matches.
        """
        if not trigger_keyword or not trigger_keyword.strip():
            logger.warning(f"Trigger keyword cannot be empty for post {instagram_post_id}.")
            return False

        fixed_response_subdoc = Post._create_fixed_response_subdocument(
            trigger_keyword, comment_response_text, direct_response_text
        )

        try:
            # Check if a fixed response with this trigger already exists
            query = {"id": instagram_post_id, "fixed_responses.trigger_keyword": trigger_keyword}
            if client_username:
                query["client_username"] = client_username
            
            post = db[POSTS_COLLECTION].find_one(query)

            if post:
                # Update existing fixed response
                update_query = {"id": instagram_post_id, "fixed_responses.trigger_keyword": trigger_keyword}
                if client_username:
                    update_query["client_username"] = client_username
                    
                result = db[POSTS_COLLECTION].update_one(
                    update_query,
                    {"$set": {
                        "fixed_responses.$.comment_response_text": fixed_response_subdoc["comment_response_text"],
                        "fixed_responses.$.direct_response_text": fixed_response_subdoc["direct_response_text"],
                        "fixed_responses.$.updated_at": fixed_response_subdoc["updated_at"]
                    }}
                )
                if result.matched_count == 0:
                    logger.warning(f"No fixed response found with trigger '{trigger_keyword}' for post {instagram_post_id} to update.")
                    return False
                logger.info(f"Fixed response for post {instagram_post_id} with trigger '{trigger_keyword}' updated. Modified: {result.modified_count > 0}")
                return result.modified_count > 0
            else:
                # Add new fixed response to the array
                add_query = {"id": instagram_post_id}
                if client_username:
                    add_query["client_username"] = client_username
                    
                result = db[POSTS_COLLECTION].update_one(
                    add_query,
                    {"$push": {"fixed_responses": fixed_response_subdoc}}
                )
                if result.matched_count == 0:
                    logger.warning(f"No post found with Instagram ID {instagram_post_id} to add fixed response.")
                    return False
                logger.info(f"New fixed response added to post {instagram_post_id} with trigger '{trigger_keyword}'. Modified: {result.modified_count > 0}")
                return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to add/update fixed response for post {instagram_post_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_fixed_responses(instagram_post_id, client_username=None):
        """Get all fixed responses for a post by its Instagram ID."""
        post = Post.get_by_instagram_id(instagram_post_id, client_username)
        if post:
            return post.get('fixed_responses', []) # Returns the array, or empty list if not found
        return []

    @staticmethod
    @with_db
    def delete_fixed_response(instagram_post_id, trigger_keyword, client_username=None):
        """Deletes a specific fixed response from a post by its Instagram ID and trigger_keyword."""
        try:
            query = {"id": instagram_post_id}
            if client_username:
                query["client_username"] = client_username
                
            result = db[POSTS_COLLECTION].update_one(
                query,
                {"$pull": {"fixed_responses": {"trigger_keyword": trigger_keyword}}}
            )
            if result.matched_count == 0:
                logger.warning(f"No post found with Instagram ID {instagram_post_id} to delete fixed response.")
                return False
            logger.info(f"Fixed response with trigger '{trigger_keyword}' deleted from post {instagram_post_id}. Modified: {result.modified_count > 0}")
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete fixed response for post {instagram_post_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all_fixed_responses_structured(client_username=None):
        """
        Return all fixed responses for posts in the format:
        {
            instagram_post_id: {
                trigger1: {"comment": ..., "DM": ...},
                trigger2: {"comment": ..., "DM": ...},
                ...
            },
            ...
        }
        """
        query = {"fixed_responses": {"$exists": True, "$ne": []}}
        if client_username:
            query["client_username"] = client_username
            
        posts_with_responses = db[POSTS_COLLECTION].find(query)
        result = {}
        for post_doc in posts_with_responses:
            post_insta_id = post_doc.get("id")
            fixed_responses_list = post_doc.get("fixed_responses", [])
            if post_insta_id and fixed_responses_list:
                result[post_insta_id] = {}
                for fr in fixed_responses_list:
                    trigger = fr.get("trigger_keyword")
                    comment = fr.get("comment_response_text")
                    dm = fr.get("direct_response_text")
                    if trigger:
                        result[post_insta_id][trigger] = {"comment": comment, "DM": dm}
        return result

    # --- Label Methods ---
    @staticmethod
    @with_db
    def set_label(instagram_post_id, label, client_username=None):
        """Set the label for a post by its Instagram ID."""
        return Post.update(instagram_post_id, {"label": str(label).strip() if label is not None else ""}, client_username)

    @staticmethod
    @with_db
    def remove_label(instagram_post_id, client_username=None):
        """Remove the label (set to empty string) for a post by its Instagram ID."""
        return Post.update(instagram_post_id, {"label": ""}, client_username)

    @staticmethod
    @with_db
    def unset_all_labels(client_username=None):
        """Unset labels (set to empty string) from all posts."""
        try:
            query = {"label": {"$exists": True, "$ne": ""}}
            if client_username:
                query["client_username"] = client_username
                
            result = db[POSTS_COLLECTION].update_many(
                query, # Only update posts that have a non-empty label
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
    def set_admin_explanation(instagram_post_id, explanation, client_username=None):
        """Set the admin explanation for a post by its Instagram ID."""
        return Post.update(instagram_post_id, {"admin_explanation": explanation.strip() if explanation else None}, client_username)

    @staticmethod
    @with_db
    def get_admin_explanation(instagram_post_id, client_username=None):
        """Get the admin explanation for a post by its Instagram ID."""
        post = Post.get_by_instagram_id(instagram_post_id, client_username)
        if post:
            return post.get('admin_explanation')
        return None

    @staticmethod
    @with_db
    def remove_admin_explanation(instagram_post_id, client_username=None):
        """Remove (nullify) the admin explanation for a post by its Instagram ID."""
        return Post.update(instagram_post_id, {"admin_explanation": None}, client_username)

    @staticmethod
    @with_db
    def get_post_ids(client_username=None):
        """Get all Instagram post IDs."""
        try:
            query = {}
            if client_username:
                query["client_username"] = client_username
            return [post['id'] for post in db[POSTS_COLLECTION].find(query, {"id": 1})]
        except PyMongoError as e:
            logger.error(f"Failed to retrieve all Instagram post IDs: {str(e)}")
            return []
