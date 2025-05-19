from .database import db, STORIES_COLLECTION, FIXED_RESPONSES_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Story:
    """Story model for MongoDB.
    Stories are stored in STORIES_COLLECTION.
    Fixed responses for stories are stored in a separate FIXED_RESPONSES_COLLECTION.
    """

    @staticmethod
    def create_story_document(story_id, media_type, caption, media_url, like_count=0, thumbnail_url=None, timestamp=None, label=None, admin_explanation=None):
        """Helper to create a new story document structure."""
        return {
            "id": story_id,  # The unique integer from Meta
            "media_type": media_type,
            "caption": caption,
            "media_url" : media_url,
            "like_count": like_count,
            "thumbnail_url": thumbnail_url,
            "timestamp": timestamp if timestamp else datetime.now(timezone.utc),
            "label": str(label).strip() if label is not None else "", # Stored in the story document
            "admin_explanation": admin_explanation # Stored in the story document
            # Fixed responses are NOT stored here, but in FIXED_RESPONSES_COLLECTION
        }

    @staticmethod
    @with_db
    def create(story_id, media_type, caption, media_url, like_count=0, thumbnail_url=None, timestamp=None, label=None, admin_explanation=None):
        """Create a new story in STORIES_COLLECTION."""
        story_doc = Story.create_story_document(story_id, media_type, caption, media_url, like_count, thumbnail_url, timestamp, label, admin_explanation)
        try:
            result = db[STORIES_COLLECTION].insert_one(story_doc)
            if result.acknowledged:
                story_doc["_id"] = result.inserted_id
                logger.info(f"Story created with Instagram ID: {story_id}, MongoDB _id: {result.inserted_id}")
                return story_doc
            logger.warning(f"Story creation not acknowledged for Instagram ID: {story_id}")
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create story for Instagram ID {story_id}: {str(e)}")
            return None

    @staticmethod
    @with_db
    def update(instagram_story_id, update_data):
        """Update a story by its Instagram ID in STORIES_COLLECTION.
        Used for labels, admin_explanation, or other direct fields of the story itself.
        """
        try:
            result = db[STORIES_COLLECTION].update_one(
                {"id": instagram_story_id}, # Query by Instagram ID
                {"$set": update_data}
            )
            if result.matched_count == 0:
                logger.warning(f"No story found with Instagram ID {instagram_story_id} to update.")
                return False
            logger.info(f"Story {instagram_story_id} updated. Modified count: {result.modified_count}")
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update story {instagram_story_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def create_or_update_from_instagram(instagram_story_data):
        """Create or update a story from Instagram API data in STORIES_COLLECTION,
        preserving existing label and admin_explanation if not provided by API data.
        Fixed responses are handled separately.
        """
        instagram_id = instagram_story_data['id']
        existing_story = db[STORIES_COLLECTION].find_one({"id": instagram_id})

        api_data = {
            "media_type": instagram_story_data.get('media_type', ''),
            "caption": instagram_story_data.get('caption', ''),
            "media_url" : instagram_story_data.get('media_url', ''),
            "like_count": instagram_story_data.get('like_count', 0), # Usually not available for stories via API
            "thumbnail_url": instagram_story_data.get('thumbnail_url', ''),
            "timestamp": instagram_story_data.get('timestamp'), # This is important for stories
        }

        if existing_story:
            update_payload = {"$set": api_data}
            # If admin_explanation or label is in instagram_story_data, include it (unlikely from API)
            if 'admin_explanation' in instagram_story_data:
                 update_payload["$set"]['admin_explanation'] = instagram_story_data['admin_explanation']
            if 'label' in instagram_story_data:
                update_payload["$set"]['label'] = str(instagram_story_data['label']).strip()

            result = db[STORIES_COLLECTION].update_one(
                {"_id": existing_story['_id']},
                update_payload
            )
            logger.info(f"Story {instagram_id} updated from Instagram data. Modified: {result.modified_count > 0}")
            return result
        else:
            new_story_doc = Story.create_story_document(
                story_id=instagram_id,
                media_type=api_data['media_type'],
                caption=api_data['caption'],
                media_url=api_data['media_url'],
                like_count=api_data['like_count'],
                thumbnail_url=api_data['thumbnail_url'],
                timestamp=api_data['timestamp'],
                label=instagram_story_data.get('label'), # if provided by API (unlikely)
                admin_explanation=instagram_story_data.get('admin_explanation') # if provided by API (unlikely)
            )
            result = db[STORIES_COLLECTION].insert_one(new_story_doc)
            logger.info(f"New story {instagram_id} created from Instagram data. Inserted ID: {result.inserted_id}")
            return result

    @staticmethod
    @with_db
    def get_by_mongo_id(mongo_id):
        """Get a story by its MongoDB _id from STORIES_COLLECTION."""
        try:
            return db[STORIES_COLLECTION].find_one({"_id": ObjectId(mongo_id)})
        except PyMongoError as e:
            logger.error(f"Failed to retrieve story by MongoDB _id {mongo_id}: {str(e)}")
            return None
        except Exception: # Invalid ObjectId format
            logger.error(f"Invalid MongoDB _id format: {mongo_id}")
            return None

    @staticmethod
    @with_db
    def get_by_instagram_id(instagram_id):
        """Get a story by its Instagram ID from STORIES_COLLECTION."""
        try:
            return db[STORIES_COLLECTION].find_one({"id": instagram_id})
        except PyMongoError as e:
            logger.error(f"Failed to retrieve story by Instagram ID {instagram_id}: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete_by_mongo_id(mongo_id):
        """Delete a story by its MongoDB _id from STORIES_COLLECTION.
        Also deletes associated fixed responses from FIXED_RESPONSES_COLLECTION.
        """
        try:
            story_to_delete = Story.get_by_mongo_id(mongo_id) # Fetches from STORIES_COLLECTION
            if story_to_delete and story_to_delete.get("id"):
                # Delete associated fixed response from FIXED_RESPONSES_COLLECTION
                Story.delete_fixed_response(story_to_delete.get("id")) 

            result = db[STORIES_COLLECTION].delete_one({"_id": ObjectId(mongo_id)})
            logger.info(f"Story with MongoDB _id {mongo_id} deleted. Count: {result.deleted_count}")
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete story by MongoDB _id {mongo_id}: {str(e)}")
            return False
        except Exception: # Invalid ObjectId format
            logger.error(f"Invalid MongoDB _id format for deletion: {mongo_id}")
            return False
            
    @staticmethod
    @with_db
    def delete_by_instagram_id(instagram_id):
        """Delete a story by its Instagram ID from STORIES_COLLECTION.
        Also deletes associated fixed responses from FIXED_RESPONSES_COLLECTION.
        """
        try:
            # Delete associated fixed response first from FIXED_RESPONSES_COLLECTION
            Story.delete_fixed_response(instagram_id) 
            # Then delete the story itself from STORIES_COLLECTION
            result = db[STORIES_COLLECTION].delete_many({"id": instagram_id}) # Use delete_many for safety, though 'id' should be unique
            logger.info(f"Stories with Instagram ID {instagram_id} deleted from STORIES_COLLECTION. Count: {result.deleted_count}")
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete story by Instagram ID {instagram_id}: {str(e)}")
            return False


    @staticmethod
    @with_db
    def get_all():
        """Get all stories from STORIES_COLLECTION."""
        try:
            # Sort by timestamp descending (newest first)
            return list(db[STORIES_COLLECTION].find().sort("timestamp", -1))
        except PyMongoError as e:
            logger.error(f"Failed to retrieve all stories: {str(e)}")
            return []

    # --- Fixed Response Methods (using FIXED_RESPONSES_COLLECTION) ---
    @staticmethod
    def _create_fixed_response_document(
        instagram_story_id,
        trigger_keyword,
        direct_response_text=None # Stories only have DM responses
    ):
        """Helper to create a new fixed response document for the separate collection."""
        return {
            "story_id": instagram_story_id,  # Links to the story's Instagram ID
            "trigger_keyword": trigger_keyword.strip(),
            "direct_response_text": direct_response_text.strip() if direct_response_text else None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

    @staticmethod
    @with_db
    def set_fixed_response(
        instagram_story_id,
        trigger_keyword,
        direct_response_text=None # Stories only have DM responses
    ):
        """Set or update a fixed response for a specific story by its Instagram ID
        in the FIXED_RESPONSES_COLLECTION.
        """
        if not trigger_keyword or not trigger_keyword.strip():
            logger.warning(f"Trigger keyword cannot be empty for story {instagram_story_id}.")
            return False

        query = {"story_id": instagram_story_id}
        # Data to be set on update or insert
        update_values = {
            "trigger_keyword": trigger_keyword.strip(),
            "direct_response_text": direct_response_text.strip() if direct_response_text else None,
            "updated_at": datetime.now(timezone.utc)
        }
        # Data to be set only on insert
        set_on_insert_values = {
             "story_id": instagram_story_id, # Ensure story_id is set on insert
             "created_at": datetime.now(timezone.utc)
        }
        
        update_operation = {
            "$set": update_values,
            "$setOnInsert": set_on_insert_values
        }
        
        try:
            result = db[FIXED_RESPONSES_COLLECTION].update_one(query, update_operation, upsert=True)
            
            if result.upserted_id:
                logger.info(f"Fixed response created for story {instagram_story_id} with new _id {result.upserted_id} in {FIXED_RESPONSES_COLLECTION}.")
            elif result.modified_count > 0:
                logger.info(f"Fixed response updated for story {instagram_story_id} in {FIXED_RESPONSES_COLLECTION}.")
            elif result.matched_count > 0:
                 logger.info(f"Fixed response for story {instagram_story_id} in {FIXED_RESPONSES_COLLECTION} matched but not modified (data was the same).")
            else: # Should not happen with upsert=True unless there's an error or nothing to do
                logger.warning(f"Fixed response operation for story {instagram_story_id} in {FIXED_RESPONSES_COLLECTION} resulted in no change and no upsert.")
            return result.acknowledged # Returns True if write was acknowledged
        except PyMongoError as e:
            logger.error(f"Failed to set fixed response for story {instagram_story_id} in {FIXED_RESPONSES_COLLECTION}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_fixed_response(instagram_story_id):
        """Get a fixed response for a specific story by its Instagram ID
        from FIXED_RESPONSES_COLLECTION.
        """
        try:
            return db[FIXED_RESPONSES_COLLECTION].find_one({"story_id": instagram_story_id})
        except PyMongoError as e:
            logger.error(f"Failed to get fixed response for story {instagram_story_id} from {FIXED_RESPONSES_COLLECTION}: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete_fixed_response(instagram_story_id):
        """Delete the fixed response for a specific story by its Instagram ID
        from FIXED_RESPONSES_COLLECTION.
        """
        try:
            result = db[FIXED_RESPONSES_COLLECTION].delete_one({"story_id": instagram_story_id})
            if result.deleted_count > 0:
                logger.info(f"Fixed response for story {instagram_story_id} deleted from {FIXED_RESPONSES_COLLECTION}.")
            else:
                logger.info(f"No fixed response found for story {instagram_story_id} in {FIXED_RESPONSES_COLLECTION} to delete.")
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete fixed response for story {instagram_story_id} from {FIXED_RESPONSES_COLLECTION}: {str(e)}")
            return False
    
    @staticmethod
    @with_db
    def get_all_fixed_responses_structured():
        """
        Return all fixed responses for stories from FIXED_RESPONSES_COLLECTION in the format:
        {
            instagram_story_id: {"trigger_keyword": ..., "direct_response_text": ...},
            ...
        }
        """
        try:
            all_fixed_responses = db[FIXED_RESPONSES_COLLECTION].find()
            result = {}
            for resp_doc in all_fixed_responses:
                story_insta_id = resp_doc.get("story_id")
                if story_insta_id:
                    result[story_insta_id] = {
                        "trigger_keyword": resp_doc.get("trigger_keyword"),
                        "direct_response_text": resp_doc.get("direct_response_text")
                        # No "comment_response_text" field for stories
                    }
            return result
        except PyMongoError as e:
            logger.error(f"Failed to get all structured fixed responses for stories from {FIXED_RESPONSES_COLLECTION}: {str(e)}")
            return {}

    # --- Label Methods (for labels stored in STORIES_COLLECTION) ---
    @staticmethod
    @with_db
    def set_label(instagram_story_id, label):
        """Set the label for a story by its Instagram ID."""
        return Story.update(instagram_story_id, {"label": str(label).strip() if label is not None else ""})

    @staticmethod
    @with_db
    def remove_label(instagram_story_id):
        """Remove the label (set to empty string) for a story by its Instagram ID."""
        return Story.update(instagram_story_id, {"label": ""})

    @staticmethod
    @with_db
    def unset_all_labels():
        """Unset labels (set to empty string) from all stories in STORIES_COLLECTION."""
        try:
            result = db[STORIES_COLLECTION].update_many(
                {"label": {"$exists": True, "$ne": ""}}, # Only update stories that have a non-empty label
                {"$set": {"label": ""}}
            )
            logger.info(f"Unset labels for {result.modified_count} stories.")
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"Failed to unset all story labels: {str(e)}")
            return 0

    # --- Admin Explanation Methods (for explanations stored in STORIES_COLLECTION) ---
    @staticmethod
    @with_db
    def set_admin_explanation(instagram_story_id, explanation):
        """Set the admin explanation for a story by its Instagram ID."""
        return Story.update(instagram_story_id, {"admin_explanation": explanation.strip() if explanation else None})

    @staticmethod
    @with_db
    def get_admin_explanation(instagram_story_id):
        """Get the admin explanation for a story by its Instagram ID."""
        story = Story.get_by_instagram_id(instagram_story_id) # Fetches from STORIES_COLLECTION
        if story:
            return story.get('admin_explanation')
        return None

    @staticmethod
    @with_db
    def remove_admin_explanation(instagram_story_id):
        """Remove (nullify) the admin explanation for a story by its Instagram ID."""
        return Story.update(instagram_story_id, {"admin_explanation": None})

