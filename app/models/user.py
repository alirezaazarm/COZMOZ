from datetime import datetime, timezone
from .database import db, USERS_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from .enums import UserStatus, MessageRole

logger = logging.getLogger(__name__)

class User:
    """User model for MongoDB.

    Each user is stored as an individual object with the following assets:
    1. Direct message history - text messages with roles and timestamps
    2. Comments history - post-related comments with parent references
    3. Reaction history - user reactions to various content
    4. User info - status, username, user_id, thread_id
    """

    # Status constants (for backward compatibility)
    STATUS_WAITING = UserStatus.WAITING.value
    STATUS_REPLIED = UserStatus.REPLIED.value
    STATUS_INSTAGRAM_FAILED = UserStatus.INSTAGRAM_FAILED.value
    STATUS_ASSISTANT_FAILED = UserStatus.ASSISTANT_FAILED.value
    STATUS_SCRAPED = UserStatus.SCRAPED.value

    @staticmethod
    def create_user_document(user_id, username, thread_id=None, status=UserStatus.WAITING.value):
        """Create a new user document structure"""
        document = {
            "user_id": str(user_id),
            "username": username,
            "status": status,
            "thread_id": thread_id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            # Direct message history
            "direct_messages": [],
            # Comments history
            "comments": [],
            # Reaction history
            "reactions": [],
        }
        return document

    @staticmethod
    def create_message_document(text, role=MessageRole.USER.value, media_type=None, media_url=None, timestamp=None):
        """Create a direct message document to be stored in user's direct_messages array"""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif timestamp.tzinfo is None:
            # Ensure timestamp has timezone info
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        message = {
            "text": text,
            "role": role,
            "timestamp": timestamp
        }

        # Only add media fields if they exist
        if media_url:
            message["media_url"] = media_url

        if media_type:
            message["media_type"] = media_type

        return message

    @staticmethod
    def create_comment_document(post_id, comment_id, text, parent_id=None, timestamp=None, status="pending"):
        """Create a comment document to be stored in user's comments array"""
        return {
            "comment_id": comment_id,
            "post_id": post_id,
            "text": text,
            "parent_id": parent_id,
            "timestamp": timestamp or datetime.now(timezone.utc),
            "status": status,
            "reactions": []
        }
    @staticmethod
    @with_db
    def add_comment_to_user(user_id, comment_doc):
        """Add a comment document to a user's comments array,
        but only if a comment with the same comment_id does not already exist."""
        try:
            comment_id = comment_doc.get("comment_id")
            if comment_id:
                existing = db[USERS_COLLECTION].find_one(
                    {"user_id": user_id, "comments.comment_id": comment_id},
                    {"comments.$": 1}
                )
                if existing:
                    return False
            result = db[USERS_COLLECTION].update_one(
                {"user_id": user_id},
                {"$push": {"comments": comment_doc}}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to add comment to user: {str(e)}")
            return False

    @staticmethod
    def create_reaction_document(content_id, content_type, reaction_type, timestamp=None, status="pending"):
        """Create a reaction document to be stored in user's reactions array"""
        return {
            "reaction_id": str(ObjectId()),
            "content_id": content_id,
            "content_type": content_type,  # "post", "comment", "message"
            "reaction_type": reaction_type,
            "timestamp": timestamp or datetime.now(timezone.utc),
            "status": status
        }

    @staticmethod
    @with_db
    def get_by_id(user_id):
        """Get a user by ID"""
        return db[USERS_COLLECTION].find_one({"user_id": user_id})

    @staticmethod
    @with_db
    def get_by_username(username):
        """Get a user by username"""
        return db[USERS_COLLECTION].find_one({"username": username})

    @staticmethod
    @with_db
    def get_by_thread_id(thread_id):
        """Get a user by thread_id"""
        return db[USERS_COLLECTION].find_one({"thread_id": thread_id})

    @staticmethod
    @with_db
    def create(user_id, username, status, thread_id=None):
        """Create a new user"""
        user_doc = User.create_user_document(
            user_id=user_id,
            username=username,
            thread_id=thread_id,
            status=status
        )
        db[USERS_COLLECTION].insert_one(user_doc)
        return user_doc

    @staticmethod
    @with_db
    def update(user_id, update_data):
        """Update a user's data"""
        # Include the updated timestamp
        update_data["updated_at"] = datetime.now(timezone.utc)

        result = db[USERS_COLLECTION].update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    @staticmethod
    @with_db
    def update_status(user_id, status):
        """Update a user's status"""
        result = db[USERS_COLLECTION].update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        return result.modified_count > 0

    @staticmethod
    @with_db
    def add_direct_message(user_id, message_doc):
        """Add a direct message to user's direct_messages array"""
        result = db[USERS_COLLECTION].update_one(
            {"user_id": user_id},
            {"$push": {"direct_messages": message_doc}}
        )
        return result.modified_count > 0

    @staticmethod
    @with_db
    def get_waiting_users(cutoff_time=None):
        """Get users with WAITING status that have messages since cutoff_time"""
        # Build the match criteria
        match_criteria = {"status": UserStatus.WAITING.value}

        if cutoff_time:
            match_criteria["direct_messages"] = {
                "$elemMatch": {
                    "timestamp": {"$gte": cutoff_time},
                    "role": MessageRole.USER.value
                }
            }

        # Build the pipeline
        pipeline = [
            {"$match": match_criteria},
            {"$project": {"user_id": 1}}
        ]

        # Execute the pipeline
        return list(db[USERS_COLLECTION].aggregate(pipeline))

    @staticmethod
    @with_db
    def get_user_messages(user_id, limit=50):
        """Get a user's most recent messages"""
        user = db[USERS_COLLECTION].find_one(
            {"user_id": user_id},
            {"direct_messages": {"$slice": -limit}}
        )

        if not user or "direct_messages" not in user:
            return []

        messages = user.get("direct_messages", [])
        messages.sort(key=lambda x: x.get("timestamp", datetime.min))
        return messages

    @staticmethod
    @with_db
    def get_user_messages_since(user_id, cutoff_time):
        """Get a user's messages since a specific time"""
        user = db[USERS_COLLECTION].find_one({"user_id": user_id})

        if not user or "direct_messages" not in user:
            return []

        # Filter messages by timestamp
        messages = []
        for msg in user.get("direct_messages", []):
            if msg.get("timestamp", datetime.min) >= cutoff_time:
                messages.append(msg)

        # Sort by timestamp
        messages.sort(key=lambda x: x.get("timestamp", datetime.min))
        return messages

    @staticmethod
    @with_db
    def get_users_with_status(status, limit=50):
        """Get users with a specific status"""
        return list(db[USERS_COLLECTION].find(
            {"status": status},
            limit=limit
        ))

    @staticmethod
    @with_db
    def get_thread_mappings():
        """Get a dictionary mapping user_id to thread_id for all users with threads"""
        try:
            # Find all users with a thread_id
            pipeline = [
                {"$match": {"thread_id": {"$exists": True}}},
                {"$project": {"user_id": 1, "thread_id": 1, "_id": 0}}
            ]

            users = list(db[USERS_COLLECTION].aggregate(pipeline))

            # Convert to dictionary
            mappings = {str(user["user_id"]): user["thread_id"] for user in users}

            return mappings
        except PyMongoError as e:
            logger.error(f"Failed to get thread mappings: {str(e)}")
            return {}
