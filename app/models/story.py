from .database import db, STORIES_COLLECTION, with_db # FIXED_RESPONSES_COLLECTION removed
from .enums import Platform
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Story:

    @staticmethod
    def create_story_document(story_id, media_type, caption, media_url, client_username, platform, like_count=0, thumbnail_url=None, timestamp=None, label=None, admin_explanation=None):
        """Helper to create a new story document structure."""
        return {
            "id": story_id,  # The unique integer from Meta
            "media_type": media_type,
            "caption": caption,
            "media_url" : media_url,
            "client_username": client_username,  # Links story to specific client
            "platform": platform.value,
            "like_count": like_count,
            "thumbnail_url": thumbnail_url,
            "timestamp": timestamp if timestamp else datetime.now(timezone.utc),
            "label": str(label).strip() if label is not None else "",
            "admin_explanation": admin_explanation,
            "fixed_responses": [], # Changed to an array to support multiple fixed responses
        }

    @staticmethod
    @with_db
    def create(story_id, media_type, caption, media_url, client_username, platform, like_count=0, thumbnail_url=None, timestamp=None, label=None, admin_explanation=None):
        """Create a new story in STORIES_COLLECTION."""
        story_doc = Story.create_story_document(story_id, media_type, caption, media_url, client_username, platform, like_count, thumbnail_url, timestamp, label, admin_explanation)
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
    def update(instagram_story_id, update_data, client_username=None):
        """Update a story by its Instagram ID in STORIES_COLLECTION.
        Used for labels, admin_explanation, or other direct fields of the story itself.
        """
        try:
            query = {"id": instagram_story_id}
            if client_username:
                query["client_username"] = client_username

            result = db[STORIES_COLLECTION].update_one(
                query, # Query by Instagram ID and optionally client
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
    def create_or_update_from_instagram(instagram_story_data, client_username, platform=Platform.INSTAGRAM):
        """Create or update a story from Instagram API data in STORIES_COLLECTION,
        preserving existing label, admin_explanation, and fixed_responses if not provided by API data.
        """
        instagram_id = instagram_story_data['id']
        query = {"id": instagram_id}
        if client_username:
            query["client_username"] = client_username
        existing_story = db[STORIES_COLLECTION].find_one(query)

        api_data = {
            "media_type": instagram_story_data.get('media_type', ''),
            "caption": instagram_story_data.get('caption', ''),
            "media_url" : instagram_story_data.get('media_url', ''),
            "like_count": instagram_story_data.get('like_count', 0),
            "thumbnail_url": instagram_story_data.get('thumbnail_url', ''),
            "timestamp": instagram_story_data.get('timestamp'),
        }

        if existing_story:
            update_payload = {"$set": api_data}
            # If admin_explanation or label is in instagram_story_data, include it
            if 'admin_explanation' in instagram_story_data:
                 update_payload["$set"]['admin_explanation'] = instagram_story_data['admin_explanation']
            if 'label' in instagram_story_data:
                update_payload["$set"]['label'] = str(instagram_story_data['label']).strip()
            # fixed_responses is managed separately by add_fixed_response, so it's preserved unless explicitly changed

            result = db[STORIES_COLLECTION].update_one(
                {"_id": existing_story['_id']},
                update_payload
            )
            logger.info(f"Story {instagram_id} updated from Instagram data. Modified: {result.modified_count > 0}")
            return result
        else:
            # Create new story, fixed_responses will be empty list by default from create_story_document
            new_story_doc = Story.create_story_document(
                story_id=instagram_id,
                media_type=api_data['media_type'],
                caption=api_data['caption'],
                media_url=api_data['media_url'],
                client_username=client_username,
                platform=platform,
                like_count=api_data['like_count'],
                thumbnail_url=api_data['thumbnail_url'],
                timestamp=api_data['timestamp'],
                label=instagram_story_data.get('label'),
                admin_explanation=instagram_story_data.get('admin_explanation')
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
        except Exception:
            logger.error(f"Invalid MongoDB _id format: {mongo_id}")
            return None

    @staticmethod
    @with_db
    def get_by_instagram_id(instagram_id, client_username=None):
        """Get a story by its Instagram ID from STORIES_COLLECTION."""
        try:
            query = {"id": instagram_id}
            if client_username:
                query["client_username"] = client_username
            return db[STORIES_COLLECTION].find_one(query)
        except PyMongoError as e:
            logger.error(f"Failed to retrieve story by Instagram ID {instagram_id}: {str(e)}")
            return None

    @staticmethod
    @with_db
    def delete_by_mongo_id(mongo_id, client_username=None):
        """Delete a story by its MongoDB _id from STORIES_COLLECTION.
        Fixed responses are part of the document, so they're deleted with the story.
        """
        try:
            query = {"_id": ObjectId(mongo_id)}
            if client_username:
                query["client_username"] = client_username
            result = db[STORIES_COLLECTION].delete_one(query)
            logger.info(f"Story with MongoDB _id {mongo_id} deleted. Count: {result.deleted_count}")
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete story by MongoDB _id {mongo_id}: {str(e)}")
            return False
        except Exception:
            logger.error(f"Invalid MongoDB _id format for deletion: {mongo_id}")
            return False

    @staticmethod
    @with_db
    def delete_by_instagram_id(instagram_id, client_username=None):
        """Delete a story by its Instagram ID from STORIES_COLLECTION.
        Fixed responses are part of the document, so they're deleted with the story.
        """
        try:
            query = {"id": instagram_id}
            if client_username:
                query["client_username"] = client_username
            result = db[STORIES_COLLECTION].delete_many(query)
            logger.info(f"Stories with Instagram ID {instagram_id} deleted from STORIES_COLLECTION. Count: {result.deleted_count}")
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete story by Instagram ID {instagram_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all(client_username=None):
        """Get all stories from STORIES_COLLECTION."""
        try:
            query = {}
            if client_username:
                query["client_username"] = client_username
            return list(db[STORIES_COLLECTION].find(query).sort("timestamp", -1))
        except PyMongoError as e:
            logger.error(f"Failed to retrieve all stories: {str(e)}")
            return []

    # --- Fixed Response Methods (Embedded in Story Document) ---
    @staticmethod
    def _create_fixed_response_subdocument(
        trigger_keyword,
        direct_response_text=None # Stories only have DM responses
    ):
        """Helper to create a fixed response sub-document."""
        return {
            "trigger_keyword": trigger_keyword.strip(),
            "direct_response_text": direct_response_text.strip() if direct_response_text else None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

    @staticmethod
    @with_db
    def add_fixed_response(
        instagram_story_id,
        trigger_keyword,
        client_username=None,
        direct_response_text=None
    ):
        """
        Adds a new fixed response to a story or updates an existing one if the trigger_keyword matches.
        """
        if not trigger_keyword or not trigger_keyword.strip():
            logger.warning(f"Trigger keyword cannot be empty for story {instagram_story_id}.")
            return False

        fixed_response_subdoc = Story._create_fixed_response_subdocument(
            trigger_keyword, direct_response_text
        )

        try:
            # Check if a fixed response with this trigger already exists
            query = {"id": instagram_story_id, "fixed_responses.trigger_keyword": trigger_keyword}
            if client_username:
                query["client_username"] = client_username
            
            story = db[STORIES_COLLECTION].find_one(query)

            if story:
                # Update existing fixed response
                update_query = {"id": instagram_story_id, "fixed_responses.trigger_keyword": trigger_keyword}
                if client_username:
                    update_query["client_username"] = client_username
                    
                result = db[STORIES_COLLECTION].update_one(
                    update_query,
                    {"$set": {
                        "fixed_responses.$.direct_response_text": fixed_response_subdoc["direct_response_text"],
                        "fixed_responses.$.updated_at": fixed_response_subdoc["updated_at"]
                    }}
                )
                if result.matched_count == 0:
                    logger.warning(f"No fixed response found with trigger '{trigger_keyword}' for story {instagram_story_id} to update.")
                    return False
                logger.info(f"Fixed response for story {instagram_story_id} with trigger '{trigger_keyword}' updated. Modified: {result.modified_count > 0}")
                return result.modified_count > 0
            else:
                # Add new fixed response to the array
                add_query = {"id": instagram_story_id}
                if client_username:
                    add_query["client_username"] = client_username
                    
                result = db[STORIES_COLLECTION].update_one(
                    add_query,
                    {"$push": {"fixed_responses": fixed_response_subdoc}}
                )
                if result.matched_count == 0:
                    logger.warning(f"No story found with Instagram ID {instagram_story_id} to add fixed response.")
                    return False
                logger.info(f"New fixed response added to story {instagram_story_id} with trigger '{trigger_keyword}'. Modified: {result.modified_count > 0}")
                return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to add/update fixed response for story {instagram_story_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_fixed_responses(instagram_story_id, client_username=None):
        """Get all fixed responses for a story by its Instagram ID."""
        story = Story.get_by_instagram_id(instagram_story_id, client_username)
        if story:
            return story.get('fixed_responses', []) # Returns the array, or empty list if not found
        return []

    @staticmethod
    @with_db
    def delete_fixed_response(instagram_story_id, trigger_keyword, client_username=None):
        """Deletes a specific fixed response from a story by its Instagram ID and trigger_keyword."""
        try:
            query = {"id": instagram_story_id}
            if client_username:
                query["client_username"] = client_username
                
            result = db[STORIES_COLLECTION].update_one(
                query,
                {"$pull": {"fixed_responses": {"trigger_keyword": trigger_keyword}}}
            )
            if result.matched_count == 0:
                logger.warning(f"No story found with Instagram ID {instagram_story_id} to delete fixed response.")
                return False
            logger.info(f"Fixed response with trigger '{trigger_keyword}' deleted from story {instagram_story_id}. Modified: {result.modified_count > 0}")
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete fixed response for story {instagram_story_id}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all_fixed_responses_structured(client_username=None):
        """
        Return all embedded fixed responses for stories in the format:
        {
            instagram_story_id: {
                trigger1: {"direct_response_text": ...},
                trigger2: {"direct_response_text": ...},
                ...
            },
            ...
        }
        Returns only stories that have fixed responses defined.
        """
        try:
            query = {"fixed_responses": {"$ne": [], "$exists": True}}
            if client_username:
                query["client_username"] = client_username
                
            stories_with_responses = db[STORIES_COLLECTION].find(query)
            result = {}
            for story_doc in stories_with_responses:
                story_insta_id = story_doc.get("id")
                fixed_responses_list = story_doc.get("fixed_responses", [])
                if story_insta_id and fixed_responses_list:
                    result[story_insta_id] = {}
                    for fr in fixed_responses_list:
                        trigger = fr.get("trigger_keyword")
                        dm = fr.get("direct_response_text")
                        if trigger:
                            result[story_insta_id][trigger] = {"direct_response_text": dm}
            return result
        except PyMongoError as e:
            logger.error(f"Failed to get all structured fixed responses for stories: {str(e)}")
            return {}

    # --- Label Methods (for labels stored in STORIES_COLLECTION) ---
    @staticmethod
    @with_db
    def set_label(instagram_story_id, label, client_username=None):
        """Set the label for a story by its Instagram ID."""
        return Story.update(instagram_story_id, {"label": str(label).strip() if label is not None else ""}, client_username)

    @staticmethod
    @with_db
    def remove_label(instagram_story_id, client_username=None):
        """Remove the label (set to empty string) for a story by its Instagram ID."""
        return Story.update(instagram_story_id, {"label": ""}, client_username)

    @staticmethod
    @with_db
    def unset_all_labels(client_username=None):
        """Unset labels (set to empty string) from all stories in STORIES_COLLECTION."""
        try:
            query = {"label": {"$exists": True, "$ne": ""}}
            if client_username:
                query["client_username"] = client_username
                
            result = db[STORIES_COLLECTION].update_many(
                query,
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
    def set_admin_explanation(instagram_story_id, explanation, client_username=None):
        """Set the admin explanation for a story by its Instagram ID."""
        return Story.update(instagram_story_id, {"admin_explanation": explanation.strip() if explanation else None}, client_username)

    @staticmethod
    @with_db
    def get_admin_explanation(instagram_story_id, client_username=None):
        """Get the admin explanation for a story by its Instagram ID."""
        story = Story.get_by_instagram_id(instagram_story_id, client_username)
        if story:
            return story.get('admin_explanation')
        return None

    @staticmethod
    @with_db
    def remove_admin_explanation(instagram_story_id, client_username=None):
        """Remove (nullify) the admin explanation for a story by its Instagram ID."""
        return Story.update(instagram_story_id, {"admin_explanation": None}, client_username)


    @staticmethod
    @with_db
    def get_story_ids(client_username=None):
        """Get all Instagram IDs of stories from STORIES_COLLECTION."""
        try:
            query = {}
            if client_username:
                query["client_username"] = client_username
            return [story['id'] for story in db[STORIES_COLLECTION].find(query, {"id": 1})]
        except PyMongoError as e:
            logger.error(f"Failed to retrieve all Instagram story IDs: {str(e)}")
            return []
