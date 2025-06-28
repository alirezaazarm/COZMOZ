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
    STATUS_ADMIN_REPLIED = UserStatus.ADMIN_REPLIED.value
    STATUS_ASSISTANT_REPLIED = UserStatus.ASSISTANT_REPLIED.value
    STATUS_FIXED_REPLIED = UserStatus.FIXED_REPLIED.value
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
    def create_message_document(text, role=MessageRole.USER.value, media_type=None, media_url=None, timestamp=None, mid=None):
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

        # Add mid if provided (for tracking Instagram message IDs)
        if mid:
            message["mid"] = mid

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
    def check_mid_exists(user_id, mid):
        """Check if a message with the given MID exists in user's direct messages"""
        user = db[USERS_COLLECTION].find_one(
            {"user_id": user_id, "direct_messages.mid": mid},
            {"direct_messages.$": 1}
        )
        return user is not None

    @staticmethod
    @with_db
    def add_direct_message_with_mid(user_id, message_doc, mid):
        """Add a direct message with MID to user's direct_messages array"""
        message_doc["mid"] = mid
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

    @staticmethod
    @with_db
    def get_message_statistics_by_role(time_frame="daily", days_back=7):
        """Get message statistics grouped by role and time frame"""
        try:
            from datetime import timedelta
            
            # Calculate the start date
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days_back)
            
            # Define the grouping format based on time frame
            if time_frame == "hourly":
                date_format = "%Y-%m-%d %H:00:00"
                group_format = {
                    "year": {"$year": "$direct_messages.timestamp"},
                    "month": {"$month": "$direct_messages.timestamp"},
                    "day": {"$dayOfMonth": "$direct_messages.timestamp"},
                    "hour": {"$hour": "$direct_messages.timestamp"}
                }
            else:  # daily
                date_format = "%Y-%m-%d"
                group_format = {
                    "year": {"$year": "$direct_messages.timestamp"},
                    "month": {"$month": "$direct_messages.timestamp"},
                    "day": {"$dayOfMonth": "$direct_messages.timestamp"}
                }
            
            pipeline = [
                # Unwind the direct_messages array
                {"$unwind": "$direct_messages"},
                # Filter messages within the time range
                {
                    "$match": {
                        "direct_messages.timestamp": {
                            "$gte": start_date,
                            "$lte": end_date
                        }
                    }
                },
                # Group by date and role
                {
                    "$group": {
                        "_id": {
                            "date": group_format,
                            "role": "$direct_messages.role"
                        },
                        "count": {"$sum": 1}
                    }
                },
                # Sort by date
                {"$sort": {"_id.date": 1}}
            ]
            
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
            
            # Process results into a more usable format
            statistics = {}
            for result in results:
                date_parts = result["_id"]["date"]
                if time_frame == "hourly":
                    date_str = f"{date_parts['year']}-{date_parts['month']:02d}-{date_parts['day']:02d} {date_parts['hour']:02d}:00:00"
                else:
                    date_str = f"{date_parts['year']}-{date_parts['month']:02d}-{date_parts['day']:02d}"
                
                role = result["_id"]["role"]
                count = result["count"]
                
                if date_str not in statistics:
                    statistics[date_str] = {}
                statistics[date_str][role] = count
            
            return statistics
            
        except PyMongoError as e:
            logger.error(f"Failed to get message statistics: {str(e)}")
            return {}

    @staticmethod
    @with_db
    def get_user_status_counts():
        """Get count of users by status"""
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
            
            # Convert to dictionary
            status_counts = {}
            for result in results:
                status = result["_id"]
                count = result["count"]
                status_counts[status] = count
            
            return status_counts
            
        except PyMongoError as e:
            logger.error(f"Failed to get user status counts: {str(e)}")
            return {}

    @staticmethod
    @with_db
    def get_user_status_counts_within_timeframe(start_date, end_date):
        """Get count of users by status within a specific timeframe based on updated_at"""
        try:
            pipeline = [
                {
                    "$match": {
                        "updated_at": {
                            "$gte": start_date,
                            "$lte": end_date
                        }
                    }
                },
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
            
            # Convert to dictionary
            status_counts = {}
            for result in results:
                status = result["_id"]
                count = result["count"]
                status_counts[status] = count
            
            return status_counts
            
        except PyMongoError as e:
            logger.error(f"Failed to get user status counts within timeframe: {str(e)}")
            return {}

    @staticmethod
    @with_db
    def get_total_users_count():
        """Get total number of users"""
        try:
            return db[USERS_COLLECTION].count_documents({})
        except PyMongoError as e:
            logger.error(f"Failed to get total users count: {str(e)}")
            return 0

    @staticmethod
    @with_db
    def get_total_users_count_within_timeframe(start_date, end_date):
        """Get total number of users within a specific timeframe based on updated_at"""
        try:
            return db[USERS_COLLECTION].count_documents({
                "updated_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            })
        except PyMongoError as e:
            logger.error(f"Failed to get total users count within timeframe: {str(e)}")
            return 0

    @staticmethod
    @with_db
    def get_message_statistics_by_role_within_timeframe(time_frame, start_date, end_date):
        """Get message statistics grouped by role and time frame within a specific date range"""
        try:
            # Define the grouping format based on time frame
            if time_frame == "hourly":
                date_format = "%Y-%m-%d %H:00:00"
                group_format = {
                    "year": {"$year": "$direct_messages.timestamp"},
                    "month": {"$month": "$direct_messages.timestamp"},
                    "day": {"$dayOfMonth": "$direct_messages.timestamp"},
                    "hour": {"$hour": "$direct_messages.timestamp"}
                }
            else:  # daily
                date_format = "%Y-%m-%d"
                group_format = {
                    "year": {"$year": "$direct_messages.timestamp"},
                    "month": {"$month": "$direct_messages.timestamp"},
                    "day": {"$dayOfMonth": "$direct_messages.timestamp"}
                }
            
            pipeline = [
                # Unwind the direct_messages array
                {"$unwind": "$direct_messages"},
                # Filter messages within the time range
                {
                    "$match": {
                        "direct_messages.timestamp": {
                            "$gte": start_date,
                            "$lte": end_date
                        }
                    }
                },
                # Group by date and role
                {
                    "$group": {
                        "_id": {
                            "date": group_format,
                            "role": "$direct_messages.role"
                        },
                        "count": {"$sum": 1}
                    }
                },
                # Sort by date
                {"$sort": {"_id.date": 1}}
            ]
            
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
            
            # Process results into a more usable format
            statistics = {}
            for result in results:
                date_parts = result["_id"]["date"]
                if time_frame == "hourly":
                    date_str = f"{date_parts['year']}-{date_parts['month']:02d}-{date_parts['day']:02d} {date_parts['hour']:02d}:00:00"
                else:
                    date_str = f"{date_parts['year']}-{date_parts['month']:02d}-{date_parts['day']:02d}"
                
                role = result["_id"]["role"]
                count = result["count"]
                
                if date_str not in statistics:
                    statistics[date_str] = {}
                statistics[date_str][role] = count
            
            return statistics
            
        except PyMongoError as e:
            logger.error(f"Failed to get message statistics within timeframe: {str(e)}")
            return {}
