import math
from datetime import datetime, timezone
from .database import db, USERS_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
from .enums import UserStatus, MessageRole, Platform

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
    STATUS_ADMIN_REPLIED = UserStatus.ADMIN_REPLIED.value
    STATUS_ASSISTANT_REPLIED = UserStatus.ASSISTANT_REPLIED.value
    STATUS_FIXED_REPLIED = UserStatus.FIXED_REPLIED.value
    STATUS_INSTAGRAM_FAILED = UserStatus.INSTAGRAM_FAILED.value
    STATUS_ASSISTANT_FAILED = UserStatus.ASSISTANT_FAILED.value
    STATUS_SCRAPED = UserStatus.SCRAPED.value

    @staticmethod
    def create_user_document(user_id, username, client_username, thread_id=None, status=UserStatus.WAITING.value, platform=None, first_name=None, last_name=None, language_code=None, is_premium=False, profile_photo_url=None):
        """Create a new user document structure"""
        if platform is None:
            raise ValueError("platform is required when creating a user document")
        document = {
            "user_id": str(user_id),
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "language_code": language_code,
            "is_premium": is_premium,
            "profile_photo_url": profile_photo_url,
            "profile_photo_last_checked": datetime.now(timezone.utc) if profile_photo_url else None,
            "client_username": client_username,  # Links user to specific client
            "platform": platform,
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
    def create_message_document(text, role=MessageRole.USER.value, media_type=None, media_url=None, timestamp=None, mid=None, message_id=None, entities=None, reply_to_message_id=None, edit_date=None):
        """Create a direct message document to be stored in user's direct_messages array"""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif timestamp.tzinfo is None:
            # Ensure timestamp has timezone info
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        message = {
            "message_id": message_id,
            "text": text,
            "role": role,
            "timestamp": timestamp
        }

        # Only add optional fields if they exist
        if media_url:
            message["media_url"] = media_url
        if media_type:
            message["media_type"] = media_type
        if mid:
            message["mid"] = mid # for Instagram
        if entities:
            message["entities"] = entities
        if reply_to_message_id:
            message["reply_to_message_id"] = reply_to_message_id
        if edit_date:
            message["edit_date"] = edit_date
            
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
    def get_by_id(user_id, client_username=None):
        """Get a user by ID, optionally filtered by client"""
        query = {"user_id": user_id}
        if client_username:
            query["client_username"] = client_username
        return db[USERS_COLLECTION].find_one(query)

    @staticmethod
    @with_db
    def get_by_username(username, client_username=None):
        """Get a user by username, optionally filtered by client"""
        query = {"username": username}
        if client_username:
            query["client_username"] = client_username
        return db[USERS_COLLECTION].find_one(query)

    @staticmethod
    @with_db
    def get_by_thread_id(thread_id, client_username=None):
        """Get a user by thread_id, optionally filtered by client"""
        query = {"thread_id": thread_id}
        if client_username:
            query["client_username"] = client_username
        return db[USERS_COLLECTION].find_one(query)

    @staticmethod
    @with_db
    def create(user_id, username, client_username, status, thread_id=None, platform=None):
        """Create a new user"""
        if platform is None:
            raise ValueError("platform is required when creating a user")
        user_doc = User.create_user_document(
            user_id=user_id,
            username=username,
            client_username=client_username,
            thread_id=thread_id,
            status=status,
            platform=platform
        )
        db[USERS_COLLECTION].insert_one(user_doc)
        return user_doc

    # -------- Platform-specific helpers --------
    @staticmethod
    def create_instagram_user(user_id, username, client_username, status, thread_id=None):
        """Create a new Instagram user"""
        return User.create(
            user_id=user_id,
            username=username,
            client_username=client_username,
            status=status,
            thread_id=thread_id,
            platform=Platform.INSTAGRAM.value,
        )

    @staticmethod
    def create_telegram_user(user_id, username, client_username, status, thread_id=None):
        """Create a new Telegram user"""
        return User.create(
            user_id=user_id,
            username=username,
            client_username=client_username,
            status=status,
            thread_id=thread_id,
            platform=Platform.TELEGRAM.value,
        )

    @staticmethod
    def create_instagram_document(user_id, username, client_username, thread_id=None, status=UserStatus.WAITING.value):
        """Create an Instagram user document (without insertion)"""
        return User.create_user_document(
            user_id=user_id,
            username=username,
            client_username=client_username,
            thread_id=thread_id,
            status=status,
            platform=Platform.INSTAGRAM.value,
        )

    @staticmethod
    def create_telegram_document(user_id, username, client_username, thread_id=None, status=UserStatus.WAITING.value, first_name=None, last_name=None, language_code=None, is_premium=False, profile_photo_url=None):
        """Create a Telegram user document (without insertion)"""
        return User.create_user_document(
            user_id=user_id,
            username=username,
            client_username=client_username,
            thread_id=thread_id,
            status=status,
            platform=Platform.TELEGRAM.value,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            is_premium=is_premium,
            profile_photo_url=profile_photo_url
        )
    
    @staticmethod
    @with_db
    def upsert_telegram_user_and_messages(user_id, client_username, user_profile_data, message_docs):
        """
        Atomically updates a Telegram user's profile and pushes new messages.
        If the user doesn't exist, they are created.
        This prevents race conditions and field conflicts.
        
        :param user_id: The Telegram user ID.
        :param client_username: The client context.
        :param user_profile_data: A dict with keys like 'username', 'first_name', etc.
        :param message_docs: A list of message documents to push.
        """
        try:
            # 1. Define the fields that should be updated on every interaction
            set_spec = {
                "status": UserStatus.WAITING.value,
                "updated_at": datetime.now(timezone.utc),
                **user_profile_data # Unpack all profile data here
            }

            # 2. Define the user document to be created ONLY if the user is new
            user_doc_on_insert = User.create_telegram_document(
                user_id=user_id,
                client_username=client_username,
                status=UserStatus.WAITING.value,
                username=user_profile_data.get('username'),
                first_name=user_profile_data.get('first_name'),
                last_name=user_profile_data.get('last_name'),
                language_code=user_profile_data.get('language_code'),
                is_premium=user_profile_data.get('is_premium', False)
            )

            # 3. IMPORTANT: Remove any keys from $setOnInsert that are also in $set to avoid conflict
            for key in set_spec.keys():
                user_doc_on_insert.pop(key, None)
            
            # Remove array keys that will be handled by $push
            user_doc_on_insert.pop("direct_messages", None)
            user_doc_on_insert.pop("comments", None)
            user_doc_on_insert.pop("reactions", None)

            # 4. Build the final update query
            update_query = {
                "$setOnInsert": user_doc_on_insert,
                "$set": set_spec
            }
            
            # 5. Add the $push operation only if there are messages to add
            if message_docs:
                update_query["$push"] = {"direct_messages": {"$each": message_docs}}

            # 6. Execute the atomic upsert operation
            result = db[USERS_COLLECTION].update_one(
                {"user_id": user_id, "client_username": client_username},
                update_query,
                upsert=True
            )
            
            return result.modified_count > 0 or result.upserted_id is not None or result.matched_count > 0

        except PyMongoError as e:
            logger.error(f"Failed to upsert Telegram user and messages: {str(e)}")
            return False
        
    @staticmethod
    @with_db
    def update(user_id, update_data, client_username=None):
        """Update a user's data"""
        # Include the updated timestamp
        update_data["updated_at"] = datetime.now(timezone.utc)

        query = {"user_id": user_id}
        if client_username:
            query["client_username"] = client_username

        result = db[USERS_COLLECTION].update_one(
            query,
            {"$set": update_data}
        )
        return result.modified_count > 0

    @staticmethod
    @with_db
    def update_status(user_id, status, client_username=None):
        """Update a user's status"""
        query = {"user_id": user_id}
        if client_username:
            query["client_username"] = client_username

        result = db[USERS_COLLECTION].update_one(
            query,
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
    def add_direct_message(user_id, message_doc, client_username=None):
        """Add a direct message to user's direct_messages array"""
        query = {"user_id": user_id}
        if client_username:
            query["client_username"] = client_username

        result = db[USERS_COLLECTION].update_one(
            query,
            {"$push": {"direct_messages": message_doc}}
        )
        return result.modified_count > 0

    @staticmethod
    @with_db
    def check_mid_exists(user_id, mid, client_username=None):
        """Check if a message with the given MID exists in user's direct messages"""
        query = {"user_id": user_id, "direct_messages.mid": mid}
        if client_username:
            query["client_username"] = client_username

        user = db[USERS_COLLECTION].find_one(
            query,
            {"direct_messages.$": 1}
        )
        return user is not None

    @staticmethod
    @with_db
    def add_direct_message_with_mid(user_id, message_doc, mid, client_username=None):
        """Add a direct message with MID to user's direct_messages array"""
        message_doc["mid"] = mid
        query = {"user_id": user_id}
        if client_username:
            query["client_username"] = client_username

        result = db[USERS_COLLECTION].update_one(
            query,
            {"$push": {"direct_messages": message_doc}}
        )
        return result.modified_count > 0

    @staticmethod
    @with_db
    def get_waiting_users(client_username=None, cutoff_time=None):
        """Get users with WAITING status that have messages since cutoff_time"""
        # Build the match criteria
        match_criteria = {"status": UserStatus.WAITING.value}
        
        if client_username:
            match_criteria["client_username"] = client_username

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
            {"$project": {"user_id": 1, "client_username": 1}}
        ]

        # Execute the pipeline
        return list(db[USERS_COLLECTION].aggregate(pipeline))

    @staticmethod
    @with_db
    def get_user_messages(user_id, limit=50, client_username=None):
        """Get a user's most recent messages"""
        query = {"user_id": user_id}
        if client_username:
            query["client_username"] = client_username

        user = db[USERS_COLLECTION].find_one(
            query,
            {"direct_messages": {"$slice": -limit}}
        )

        if not user or "direct_messages" not in user:
            return []

        messages = user.get("direct_messages", [])
        messages.sort(key=lambda x: x.get("timestamp", datetime.min))
        return messages

    @staticmethod
    @with_db
    def get_user_messages_since(user_id, cutoff_time, client_username=None):
        """Get a user's messages since a specific time"""
        query = {"user_id": user_id}
        if client_username:
            query["client_username"] = client_username

        user = db[USERS_COLLECTION].find_one(query)

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
    def get_users_with_status(status, client_username=None, limit=50):
        """Get users with a specific status"""
        query = {"status": status}
        if client_username:
            query["client_username"] = client_username

        return list(db[USERS_COLLECTION].find(
            query,
            limit=limit
        ))
    
    @staticmethod
    @with_db
    def get_users_by_platform_for_client(platform, client_username=None):
        """Get all users for a given platform and client, projecting only necessary fields for a user list."""
        try:
            match_filter = {"platform": platform}
            if client_username:
                match_filter["client_username"] = client_username

            projection = {
                "user_id": 1,
                "username": 1,
                "first_name": 1,
                "last_name": 1,
                "profile_photo_url": 1,
                "updated_at": 1,
                "_id": 0
            }

            sort_order = [("updated_at", -1)]

            users = list(db[USERS_COLLECTION].find(match_filter, projection).sort(sort_order))
            return users
        except PyMongoError as e:
            logger.error(f"Failed to get users by platform: {str(e)}")
            return []

    @staticmethod
    @with_db
    def get_thread_mappings(client_username=None):
        """Get a dictionary mapping user_id to thread_id for all users with threads"""
        try:
            # Find all users with a thread_id
            match_criteria = {"thread_id": {"$exists": True}}
            if client_username:
                match_criteria["client_username"] = client_username

            pipeline = [
                {"$match": match_criteria},
                {"$project": {"user_id": 1, "thread_id": 1, "client_username": 1, "_id": 0}}
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
    def get_message_statistics_by_role(time_frame="daily", days_back=7, client_username=None):
        """Get message statistics grouped by role and time frame, optionally filtered by client_username"""
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
            match_filter = {
                "direct_messages.timestamp": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            if client_username:
                match_filter["client_username"] = client_username
            pipeline = [
                {"$unwind": "$direct_messages"},
                {"$match": match_filter},
                {"$group": {
                    "_id": {
                        "date": group_format,
                        "role": "$direct_messages.role"
                    },
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id.date": 1}}
            ]
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
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
    def get_user_status_counts(client_username=None):
        """Get count of users by status, optionally filtered by client_username"""
        try:
            match_filter = {}
            if client_username:
                match_filter["client_username"] = client_username
            pipeline = [
                {"$match": match_filter} if match_filter else {},
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            # Remove empty $match if not needed
            if not match_filter:
                pipeline = pipeline[1:]
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
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
    def get_user_status_counts_within_timeframe(start_date, end_date, client_username=None):
        """Get count of users by status within a specific timeframe based on updated_at, optionally filtered by client_username"""
        try:
            match_filter = {
                "updated_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            if client_username:
                match_filter["client_username"] = client_username
            pipeline = [
                {"$match": match_filter},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
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
    def get_total_users_count(client_username=None):
        """Get total number of users, optionally filtered by client_username"""
        try:
            match_filter = {}
            if client_username:
                match_filter["client_username"] = client_username
            return db[USERS_COLLECTION].count_documents(match_filter)
        except PyMongoError as e:
            logger.error(f"Failed to get total users count: {str(e)}")
            return 0

    @staticmethod
    @with_db
    def get_total_users_count_within_timeframe(start_date, end_date, client_username=None):
        """Get total number of users within a specific timeframe based on updated_at, optionally filtered by client_username"""
        try:
            match_filter = {
                "updated_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            if client_username:
                match_filter["client_username"] = client_username
            return db[USERS_COLLECTION].count_documents(match_filter)
        except PyMongoError as e:
            logger.error(f"Failed to get total users count within timeframe: {str(e)}")
            return 0

    @staticmethod
    @with_db
    def get_message_statistics_by_role_within_timeframe(time_frame, start_date, end_date, client_username=None):
        """Get message statistics grouped by role and time frame within a specific date range, optionally filtered by client_username"""
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
            match_filter = {
                "direct_messages.timestamp": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            if client_username:
                match_filter["client_username"] = client_username
            pipeline = [
                {"$unwind": "$direct_messages"},
                {"$match": match_filter},
                {"$group": {
                    "_id": {
                        "date": group_format,
                        "role": "$direct_messages.role"
                    },
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id.date": 1}}
            ]
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
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

    @staticmethod
    @with_db
    def get_message_statistics_by_role_within_timeframe_by_platform(time_frame, start_date, end_date, platform, client_username=None):
        """Get message statistics by role, time frame, and platform"""
        try:
            if time_frame == "hourly":
                group_format = {
                    "year": {"$year": "$direct_messages.timestamp"},
                    "month": {"$month": "$direct_messages.timestamp"},
                    "day": {"$dayOfMonth": "$direct_messages.timestamp"},
                    "hour": {"$hour": "$direct_messages.timestamp"}
                }
            else:
                group_format = {
                    "year": {"$year": "$direct_messages.timestamp"},
                    "month": {"$month": "$direct_messages.timestamp"},
                    "day": {"$dayOfMonth": "$direct_messages.timestamp"}
                }
            match_filter = {
                "platform": platform,
                "direct_messages.timestamp": {"$gte": start_date, "$lte": end_date}
            }
            if client_username:
                match_filter["client_username"] = client_username
            pipeline = [
                {"$unwind": "$direct_messages"},
                {"$match": match_filter},
                {"$group": {
                    "_id": {
                        "date": group_format,
                        "role": "$direct_messages.role"
                    },
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id.date": 1}}
            ]
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
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
            logger.error(f"Failed to get message statistics by platform: {str(e)}")
            return {}

    @staticmethod
    @with_db
    def get_user_status_counts_by_platform(platform, client_username=None):
        """Get user status counts by platform"""
        try:
            match_filter = {"platform": platform}
            if client_username:
                match_filter["client_username"] = client_username
            pipeline = [
                {"$match": match_filter},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}}
            ]
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
            return {result["_id"]: result["count"] for result in results}
        except PyMongoError as e:
            logger.error(f"Failed to get user status counts by platform: {str(e)}")
            return {}

    @staticmethod
    @with_db
    def get_user_status_counts_within_timeframe_by_platform(start_date, end_date, platform, client_username=None):
        """Get user status counts within a timeframe by platform"""
        try:
            match_filter = {
                "platform": platform,
                "updated_at": {"$gte": start_date, "$lte": end_date}
            }
            if client_username:
                match_filter["client_username"] = client_username
            pipeline = [
                {"$match": match_filter},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}}
            ]
            results = list(db[USERS_COLLECTION].aggregate(pipeline))
            return {result["_id"]: result["count"] for result in results}
        except PyMongoError as e:
            logger.error(f"Failed to get user status counts by platform and timeframe: {str(e)}")
            return {}

    @staticmethod
    @with_db
    def get_total_users_count_by_platform(platform, client_username=None):
        """Get total user count by platform"""
        try:
            match_filter = {"platform": platform}
            if client_username:
                match_filter["client_username"] = client_username
            return db[USERS_COLLECTION].count_documents(match_filter)
        except PyMongoError as e:
            logger.error(f"Failed to get total users count by platform: {str(e)}")
            return 0

    @staticmethod
    @with_db
    def get_total_users_count_within_timeframe_by_platform(start_date, end_date, platform, client_username=None):
        """Get total user count within a timeframe by platform"""
        try:
            match_filter = {
                "platform": platform,
                "updated_at": {"$gte": start_date, "$lte": end_date}
            }
            if client_username:
                match_filter["client_username"] = client_username
            return db[USERS_COLLECTION].count_documents(match_filter)
        except PyMongoError as e:
            logger.error(f"Failed to get total users count by platform and timeframe: {str(e)}")
            return 0
    
    @staticmethod
    @with_db
    def get_paginated_users_by_platform(platform, client_username, page=1, limit=25, status_filter=None):
        """
        Retrieves a paginated and filtered list of users for a specific platform and client.

        Args:
            platform (str): The platform to filter by (e.g., 'instagram').
            client_username (str): The client's username.
            page (int): The page number to retrieve, starting from 1.
            limit (int): The number of users to return per page.
            status_filter (str, optional): The user status to filter by. Defaults to None.

        Returns:
            dict: A dictionary containing:
                  - 'users' (list): The list of user documents.
                  - 'total_count' (int): The total number of users matching the filter.
                  - 'total_pages' (int): The total number of pages available.
        """
        try:
            # 1. Build the database query filter
            query = {
                "platform": platform,
                "client_username": client_username
            }
            
            # 2. Add the status filter if it is provided
            if status_filter:
                query["status"] = status_filter
                
            # 3. Get the total count of documents matching the query for pagination
            total_count = db[USERS_COLLECTION].count_documents(query)
            if total_count == 0:
                return {"users": [], "total_count": 0, "total_pages": 0}

            # 4. Calculate pagination details
            total_pages = math.ceil(total_count / limit)
            # Ensure page number is within a valid range
            page = max(1, min(page, total_pages))
            skip_amount = (page - 1) * limit

            # 5. Define the projection to fetch only necessary fields
            projection = {
                "user_id": 1,
                "username": 1,
                "first_name": 1,
                "last_name": 1,
                "profile_photo_url": 1,
                "updated_at": 1,
                "_id": 0  # Exclude the MongoDB ObjectId
            }
            
            # 6. Execute the query to get the paginated subset of users.
            # Sorting by 'updated_at' descending shows the most recently active users first.
            cursor = db[USERS_COLLECTION].find(
                query,
                projection
            ).sort([("updated_at", -1)]).skip(skip_amount).limit(limit)
            
            users_list = list(cursor)
                
            return {
                "users": users_list,
                "total_count": total_count,
                "total_pages": total_pages
            }
        except PyMongoError as e:
            logger.error(f"Failed to fetch paginated users for client {client_username}: {e}")
            return {"users": [], "total_count": 0, "total_pages": 0, "error": str(e)}