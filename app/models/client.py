from datetime import datetime, timezone
from .database import db, with_db
from .enums import ClientStatus, ModuleType, Platform
import logging
from pymongo.errors import PyMongoError
from bson import ObjectId
import os

logger = logging.getLogger(__name__)

# Collection name for clients
CLIENTS_COLLECTION = 'clients'

class Client:
    """Client model for multi-tenant support.
    
    Each client represents a separate business/organization with their own:
    - Social media credentials (Facebook/Instagram)
    - OpenAI assistant configuration
    - User base and data
    - Module access and settings
    """

    @staticmethod
    def create_client_document(
        username,
        business_name,
        phone_number=None,
        first_name=None,
        last_name=None,
        status=ClientStatus.INACTIVE.value,
        page_access_token=None,
        facebook_id=None,
        facebook_access_token=None,
        telegram_access_token=None,
        assistant_id=None,
        vector_store_id=None,
        modules=None,
        platforms=None,
        notes=None,
        is_admin=False,
        password=None,
        email=None,
        credentials=None,
        settings=None
    ):
        """Create a new client document structure"""
        # Default platform structures with all modules for each platform
        default_platform_modules = {
            ModuleType.FIXED_RESPONSE.value: {"enabled": True},
            ModuleType.DM_ASSIST.value: {"enabled": True},
            ModuleType.COMMENT_ASSIST.value: {"enabled": True},
            ModuleType.VISION.value: {"enabled": True},
            ModuleType.ORDERBOOK.value: {"enabled": True},
        }

        platform_struct = platforms or {
            Platform.INSTAGRAM.value: {
                "enabled": False,
                "modules": {**default_platform_modules},
            },
            Platform.TELEGRAM.value: {
                "enabled": False,
                "modules": {**default_platform_modules},
            },
        }

        document = {
            "username": username,  # Unique identifier for the client
            "status": status,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            
            # Client info (required)
            "info": {
                "phone_number": phone_number,
                "business": business_name,
                "first_name": first_name,
                "last_name": last_name,
                "email": email
            },
            
            # Keys (all API keys and credentials consolidated here)
            "keys": {
                "page_access_token": page_access_token,
                "username": username,  # Same as main username
                "ig_id": facebook_id,  # Instagram ID (not Facebook ID)
                "facebook_access_token": facebook_access_token,
                "telegram_access_token": telegram_access_token,
                "assistant_id": assistant_id,
                "vector_store_id": vector_store_id,
                "password": password  # Admin password for all clients
            },
            
            # Platform configurations (per-platform enable toggle and modules)
            "platforms": platform_struct,
            
            # Notes
            "notes": notes,
            
            # Admin functionality (all clients are admin users)
            "is_admin": True,  # All clients are admin users
            "last_login": None,
            
            # Legacy fields for backward compatibility
            "business_name": business_name,  # Keep for backward compatibility
            "email": email,  # Keep for backward compatibility
            
            # Client-specific settings
            "settings": settings or {
                "timezone": "UTC",
                "language": "en",
                "base_url": None,
                "webhook_url": None,
                "notification_settings": {
                    "email_notifications": True,
                    "sms_notifications": False
                }
            },
            
            # Usage statistics
            "usage_stats": {
                "total_users": 0,
                "total_messages": 0,
                "total_posts": 0,
                "last_activity": None
            },
            
            # Billing information (for future use)
            "billing": {
                "plan": "basic",
                "billing_cycle": "monthly",
                "next_billing_date": None,
                "payment_status": "active"
            },
            # Logs for audit trail
            "logs": []
        }
        return document



    @staticmethod
    def _validate_platform_requirements(platforms, keys):
        """Validate that required keys are present for enabled platforms.
        Returns a list of error strings; empty list if valid.
        """
        errors = []
        platforms = platforms or {}
        keys = keys or {}

        instagram = platforms.get(Platform.INSTAGRAM.value, {})
        if instagram.get("enabled"):
            required_ig_keys = ["page_access_token", "username", "ig_id", "facebook_access_token"]
            missing = [k for k in required_ig_keys if not keys.get(k)]
            if missing:
                errors.append(
                    f"Instagram enabled but missing required keys: {', '.join(missing)}"
                )

        telegram = platforms.get(Platform.TELEGRAM.value, {})
        if telegram.get("enabled"):
            if not keys.get("telegram_access_token"):
                errors.append("Telegram enabled but missing required key: telegram_access_token")

        return errors

    @staticmethod
    @with_db
    def create(username, business_name=None, **kwargs):
        """Create a new client"""
        try:
            # Check if username already exists
            if Client.get_by_username(username):
                logger.error(f"Client with username {username} already exists")
                return None
            
            client_doc = Client.create_client_document(
                username=username,
                business_name=business_name,
                **kwargs
            )
            # Validate platform requirements
            errors = Client._validate_platform_requirements(
                client_doc.get("platforms"), client_doc.get("keys")
            )
            if errors:
                logger.error("; ".join(errors))
                return None
            
            result = db[CLIENTS_COLLECTION].insert_one(client_doc)
            if result.acknowledged:
                client_doc['_id'] = result.inserted_id
                logger.info(f"Created new client: {username}")
                return client_doc
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create client: {str(e)}")
            return None

    @staticmethod
    @with_db
    def get_by_username(username):
        """Get a client by username"""
        try:
            return db[CLIENTS_COLLECTION].find_one({"username": username})
        except PyMongoError as e:
            logger.error(f"Failed to get client by username: {str(e)}")
            return None

    @staticmethod
    @with_db
    def get_by_id(client_id):
        """Get a client by ID"""
        try:
            return db[CLIENTS_COLLECTION].find_one({"_id": ObjectId(client_id)})
        except PyMongoError as e:
            logger.error(f"Failed to get client by ID: {str(e)}")
            return None

    @staticmethod
    @with_db
    def get_by_email(email):
        """Get a client by email"""
        try:
            return db[CLIENTS_COLLECTION].find_one({"email": email})
        except PyMongoError as e:
            logger.error(f"Failed to get client by email: {str(e)}")
            return None

    @staticmethod
    @with_db
    def update(username, update_data):
        """Update a client's data"""
        try:
            # Include the updated timestamp
            update_data["updated_at"] = datetime.now(timezone.utc)
            
            # Validate platform requirements if platforms or keys are being updated
            if "platforms" in update_data or "keys" in update_data:
                current = Client.get_by_username(username) or {}
                new_platforms = update_data.get("platforms", current.get("platforms") or {})
                new_keys = update_data.get("keys", current.get("keys") or {})
                
                errors = Client._validate_platform_requirements(new_platforms, new_keys)
                if errors:
                    logger.error("; ".join(errors))
                    return False
            
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update client: {str(e)}")
            return False

    @staticmethod
    @with_db
    def update_credentials(username, credential_type, credentials):
        """Update client credentials in keys section"""
        try:
            update_data = {
                f"keys.{credential_type}": credentials,
                "updated_at": datetime.now(timezone.utc)
            }
            
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update client credentials: {str(e)}")
            return False

    # update_module_settings method removed - these modules don't have settings, only enabled status



    @staticmethod
    @with_db
    def update_usage_stats(username, stats_update):
        """Update usage statistics for a client"""
        try:
            update_data = {}
            for key, value in stats_update.items():
                update_data[f"usage_stats.{key}"] = value
            
            update_data["usage_stats.last_activity"] = datetime.now(timezone.utc)
            update_data["updated_at"] = datetime.now(timezone.utc)
            
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update usage stats: {str(e)}")
            return False

    @staticmethod
    @with_db
    def increment_usage_stats(username, **increments):
        """Increment usage statistics for a client"""
        try:
            inc_data = {}
            for key, value in increments.items():
                inc_data[f"usage_stats.{key}"] = value
            
            update_data = {
                "usage_stats.last_activity": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {
                    "$inc": inc_data,
                    "$set": update_data
                }
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to increment usage stats: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all_active():
        """Get all active clients"""
        try:
            return list(db[CLIENTS_COLLECTION].find(
                {"status": ClientStatus.ACTIVE.value}
            ))
        except PyMongoError as e:
            logger.error(f"Failed to get active clients: {str(e)}")
            return []

    @staticmethod
    @with_db
    def get_clients_with_module_enabled(module_name):
        """Get all clients with a specific module enabled"""
        try:
            return list(db[CLIENTS_COLLECTION].find({
                "status": ClientStatus.ACTIVE.value,
                f"modules.{module_name}.enabled": True
            }))
        except PyMongoError as e:
            logger.error(f"Failed to get clients with module enabled: {str(e)}")
            return []

    @staticmethod
    @with_db
    def delete(username):
        """Delete a client (hard delete - permanently removes from database)"""
        try:
            result = db[CLIENTS_COLLECTION].delete_one({"username": username})
            if result.deleted_count > 0:
                logger.info(f"Client {username} permanently deleted from database")
                return True
            else:
                logger.warning(f"Client {username} not found for deletion")
                return False
        except PyMongoError as e:
            logger.error(f"Failed to delete client: {str(e)}")
            return False

    @staticmethod
    @with_db
    def soft_delete(username):
        """Soft delete a client (changes status to deleted but keeps in database)"""
        try:
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {
                    "$set": {
                        "status": ClientStatus.DELETED.value,
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            if result.modified_count > 0:
                logger.info(f"Client {username} soft deleted (status changed to deleted)")
                return True
            else:
                logger.warning(f"Client {username} not found for soft deletion")
                return False
        except PyMongoError as e:
            logger.error(f"Failed to soft delete client: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_client_credentials(username, credential_type=None):
        """Get client credentials from keys section"""
        try:
            client = db[CLIENTS_COLLECTION].find_one(
                {"username": username},
                {"keys": 1}
            )
            
            if not client or "keys" not in client:
                return None
                
            if credential_type:
                return client["keys"].get(credential_type)
            return client["keys"]
        except PyMongoError as e:
            logger.error(f"Failed to get client credentials: {str(e)}")
            return None


    @staticmethod
    @with_db
    def get_client_by_ig_id(ig_id):
        """Find client username by Instagram ID"""
        try:
            # Search for client with matching ig_id in keys
            from ..models.database import db, CLIENTS_COLLECTION
            client = db[CLIENTS_COLLECTION].find_one(
                {"keys.ig_id": ig_id, "status": "active"},
                {"username": 1}
            )
            if client:
                return client["username"]
            return None
        except Exception as e:
            logger.error(f"Error finding client by ig_id {ig_id}: {str(e)}")
            return None
    

    @staticmethod
    @with_db
    def is_module_enabled(username, module_name):
        """Check if a module is enabled for a client by checking all platforms"""
        try:
            client = db[CLIENTS_COLLECTION].find_one(
                {"username": username},
                {"platforms": 1}
            )
            
            if not client or "platforms" not in client:
                return False
            
            # Check if module is enabled on any platform
            platforms = client["platforms"]
            for platform_name, platform_cfg in platforms.items():
                if platform_cfg.get("enabled"):
                    modules = platform_cfg.get("modules", {})
                    if module_name in modules and modules[module_name].get("enabled"):
                        return True
            return False
        except PyMongoError as e:
            logger.error(f"Failed to check module status: {str(e)}")
            return False

    # get_module_settings method removed - these modules don't have settings, only enabled status

    @staticmethod
    @with_db
    def get_module_status(username, platform, module_name):
        """Get the enabled status of a specific module for a client and platform."""
        try:
            client = db[CLIENTS_COLLECTION].find_one(
                {"username": username},
                {f"platforms.{platform}.modules.{module_name}.enabled": 1}
            )
            if not client:
                return False
            
            platform_data = client.get("platforms", {}).get(platform, {})
            module_data = platform_data.get("modules", {}).get(module_name, {})
            return module_data.get("enabled", False)
        except PyMongoError as e:
            logger.error(f"Failed to get module status for {username}, {platform}, {module_name}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def update_module_status(username, platform, module_name, enabled):
        """Update the enabled status of a specific module for a client and platform."""
        try:
            update_data = {
                f"platforms.{platform}.modules.{module_name}.enabled": bool(enabled),
                "updated_at": datetime.now(timezone.utc)
            }
            
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {"$set": update_data}
            )
            if result.modified_count > 0:
                Client.reload_main_app_memory()
                return True
            return False
        except PyMongoError as e:
            logger.error(f"Failed to update module status for {username}, {platform}, {module_name}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_platform_module_settings(username, platform):
        """Get all module settings for a given platform for a client."""
        try:
            client = db[CLIENTS_COLLECTION].find_one(
                {"username": username},
                {f"platforms.{platform}.modules": 1}
            )
            if not client:
                return {}
            
            platform_data = client.get("platforms", {}).get(platform, {})
            return platform_data.get("modules", {})
        except PyMongoError as e:
            logger.error(f"Failed to get module settings for {username}, {platform}: {str(e)}")
            return {}

    @staticmethod
    @with_db
    def get_platform_enabled_status(username, platform):
        """Get the enabled status of a specific platform for a client."""
        try:
            client = db[CLIENTS_COLLECTION].find_one(
                {"username": username},
                {f"platforms.{platform}.enabled": 1}
            )
            if not client:
                return False
            
            platform_data = client.get("platforms", {}).get(platform, {})
            return platform_data.get("enabled", False)
        except PyMongoError as e:
            logger.error(f"Failed to get platform status for {username}, {platform}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def update_platform_enabled_status(username, platform, enabled):
        """Update the enabled status of a specific platform for a client."""
        try:
            update_data = {
                f"platforms.{platform}.enabled": bool(enabled),
                "updated_at": datetime.now(timezone.utc)
            }
            
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {"$set": update_data}
            )
            if result.modified_count > 0:
                Client.reload_main_app_memory()
                return True
            return False
        except PyMongoError as e:
            logger.error(f"Failed to update platform status for {username}, {platform}: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_client_platforms_config(username):
        """Get all platform configurations for a client."""
        try:
            client = db[CLIENTS_COLLECTION].find_one(
                {"username": username},
                {"platforms": 1}
            )
            if not client:
                return {}
            
            return client.get("platforms", {})
        except PyMongoError as e:
            logger.error(f"Failed to get client platforms config for {username}: {str(e)}")
            return {}

    @staticmethod
    def reload_main_app_memory():
        """Trigger main app to reload memory from DB."""
        logging.info("Triggering main app to reload memory from DB.")
        try:
            from ..config import Config
            import requests
            
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {Config.VERIFY_TOKEN}"}
            response = requests.post(
                Config.BASE_URL + "/hooshang_update/reload-memory",
                headers=headers
            )
            if response.status_code == 200:
                logging.info("Main app memory reload triggered successfully.")
                return True
            else:
                logging.error(f"Failed to trigger main app memory reload. Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            logging.error(f"Error triggering main app memory reload: {str(e)}")
            return False

    # ===== CLIENT MANAGEMENT UTILITIES =====
    
    @staticmethod
    def create_with_credentials(username, business_name, phone_number=None, first_name=None, last_name=None, 
                               page_access_token=None, facebook_id=None, facebook_access_token=None,
                               assistant_id=None, vector_store_id=None, notes=None, **kwargs):
        """
        Create a new client with specific credentials.
        """
        try:
            # Create the client
            client = Client.create(
                username=username,
                business_name=business_name,
                phone_number=phone_number,
                first_name=first_name,
                last_name=last_name,
                page_access_token=page_access_token,
                facebook_id=facebook_id,
                facebook_access_token=facebook_access_token,
                assistant_id=assistant_id,
                vector_store_id=vector_store_id,
                notes=notes,
                **kwargs
            )
            
            if client:
                logger.info(f"Successfully created client with credentials: {username}")
                return client
            else:
                logger.error(f"Failed to create client: {username}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating client: {str(e)}")
            return None

    @staticmethod
    def get_statistics(client_username):
        """Get comprehensive statistics for a client"""
        try:
            client = Client.get_by_username(client_username)
            if not client:
                return None
            
            # Get counts from different collections
            from .database import USERS_COLLECTION, PRODUCTS_COLLECTION, POSTS_COLLECTION, STORIES_COLLECTION
            
            stats = {
                "client_info": {
                    "username": client["username"],
                    "business_name": client.get("business_name") or client.get("info", {}).get("business"),
                    "status": client["status"],
                    "created_at": client["created_at"],
                    "last_updated": client["updated_at"]
                },
                "data_counts": {
                    "users": db[USERS_COLLECTION].count_documents({"client_username": client_username}),
                    "products": db[PRODUCTS_COLLECTION].count_documents({"client_username": client_username}),
                    "posts": db[POSTS_COLLECTION].count_documents({"client_username": client_username}),
                    "stories": db[STORIES_COLLECTION].count_documents({"client_username": client_username})
                },
                "usage_stats": client.get("usage_stats", {}),
                "platforms": client.get("platforms", {}),
                "last_activity": client.get("usage_stats", {}).get("last_activity")
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get statistics for client {client_username}: {str(e)}")
            return None

    @staticmethod
    def validate_access(client_username, required_module=None):
        """
        Validate if a client exists and has access to a specific module.
        Returns: (is_valid, client_data, error_message)
        """
        try:
            client = Client.get_by_username(client_username)
            
            if not client:
                return False, None, f"Client {client_username} not found"
            
            if client["status"] != "active":
                return False, client, f"Client {client_username} is not active"
            
            if required_module:
                if not Client.is_module_enabled(client_username, required_module):
                    return False, client, f"Module {required_module} is not enabled for client {client_username}"
            
            return True, client, None
            
        except Exception as e:
            error_msg = f"Error validating client access: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

    @staticmethod
    def list_all():
        """Get a list of all clients with basic information"""
        try:
            # Get all clients (not just active ones)
            clients = list(db[CLIENTS_COLLECTION].find({}))
            client_list = []
            
            for client in clients:
                info = client.get("info", {})
                client_info = {
                    "username": client["username"],
                    "business_name": client.get("business_name") or info.get("business"),
                    "email": client.get("email") or info.get("email"),  # Check both locations for email
                    "status": client["status"],
                    "created_at": client["created_at"],
                    "updated_at": client.get("updated_at"),
                    "phone_number": info.get("phone_number"),
                    "first_name": info.get("first_name"),
                    "last_name": info.get("last_name"),
                    "notes": client.get("notes"),
                    "is_admin": client.get("is_admin", False),
                    "last_login": client.get("last_login"),
                    "keys": client.get("keys", {}),
                    "openai": client.get("openai", {}),
                    "platforms": client.get("platforms", {}),
                    "last_activity": client.get("usage_stats", {}).get("last_activity"),
                    "total_users": client.get("usage_stats", {}).get("total_users", 0),
                    "enabled_modules": [
                        module for platform_name, platform_cfg in client.get("platforms", {}).items()
                        if platform_cfg.get("enabled")
                        for module, config in platform_cfg.get("modules", {}).items()
                        if config.get("enabled", False)
                    ]
                }
                client_list.append(client_info)
            
            return client_list
            
        except Exception as e:
            logger.error(f"Failed to list clients: {str(e)}")
            return []

    # ===== ADMIN FUNCTIONALITY =====
    
    @staticmethod
    @with_db
    def create_admin(username, password, business_name=None, email=None, is_active=True):
        """Create a new admin user (admin is just a client with is_admin=True)"""
        try:
            # Check if username already exists
            if Client.get_by_username(username):
                logger.error(f"Admin with username {username} already exists")
                return None
                
            admin_doc = Client.create_client_document(
                username=username,
                business_name=business_name or f"Admin - {username}",
                email=email or f"{username}@admin.local",
                status="active" if is_active else "inactive",
                is_admin=True,
                password=password,  # Simple password storage (no hashing)
                phone_number=None,
                first_name=None,
                last_name=None,
                notes="Administrator account"
            )
            
            result = db[CLIENTS_COLLECTION].insert_one(admin_doc)
            if result.acknowledged:
                admin_doc['_id'] = result.inserted_id
                logger.info(f"Created new admin: {username}")
                return admin_doc
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create admin: {str(e)}")
            return None

    @staticmethod
    @with_db
    def authenticate_admin(username, password):
        """Authenticate an admin user by username and password"""
        try:
            admin = db[CLIENTS_COLLECTION].find_one({
                "username": username,
                "is_admin": True
            })
            
            if not admin:
                logger.warning(f"Authentication failed: Admin {username} not found")
                return None
            
            if admin.get("status") != "active":
                logger.warning(f"Authentication failed: Admin {username} is not active")
                return None
            
            # Simple password comparison (no hashing as requested)
            admin_password = admin.get("keys", {}).get("password") or admin.get("password")
            if admin_password == password:
                # Update last login time
                db[CLIENTS_COLLECTION].update_one(
                    {"_id": admin["_id"]},
                    {"$set": {"last_login": datetime.now(timezone.utc)}}
                )
                logger.info(f"Admin {username} authenticated successfully")
                return admin
            else:
                logger.warning(f"Authentication failed: Invalid password for admin {username}")
                return None
                
        except PyMongoError as e:
            logger.error(f"Failed to authenticate admin: {str(e)}")
            return None

    @staticmethod
    @with_db
    def get_all_admins():
        """Get all admin users"""
        try:
            return list(db[CLIENTS_COLLECTION].find({"is_admin": True}))
        except PyMongoError as e:
            logger.error(f"Failed to get admin users: {str(e)}")
            return []

    @staticmethod
    @with_db
    def update_admin_password(username, new_password):
        """Update an admin user's password in keys section"""
        try:
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username, "is_admin": True},
                {
                    "$set": {
                        "keys.password": new_password,  # Store password in keys section
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            
            logger.info(f"Password updated for admin {username}")
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update admin password: {str(e)}")
            return False

    @staticmethod
    @with_db
    def update_admin_status(username, is_active):
        """Update an admin user's active status"""
        try:
            status = "active" if is_active else "inactive"
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username, "is_admin": True},
                {
                    "$set": {
                        "status": status,
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            
            status_str = "activated" if is_active else "deactivated"
            logger.info(f"Admin {username} {status_str}")
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update admin status: {str(e)}")
            return False

    @staticmethod
    @with_db
    def delete_admin(username):
        """Delete an admin user (hard delete - permanently removes from database)"""
        try:
            result = db[CLIENTS_COLLECTION].delete_one({"username": username, "is_admin": True})
            if result.deleted_count > 0:
                logger.info(f"Admin {username} permanently deleted from database")
                return True
            else:
                logger.warning(f"Admin {username} not found for deletion")
                return False
        except PyMongoError as e:
            logger.error(f"Failed to delete admin: {str(e)}")
            return False

    @staticmethod
    @with_db
    def ensure_default_admin():
        """Ensure there is at least one active admin user"""
        try:
            count = db[CLIENTS_COLLECTION].count_documents({"is_admin": True})
            
            if count == 0:
                # Create default admin
                default_username = "admin"
                default_password = "admin123"  # Should be changed immediately after first login
                
                Client.create_admin(default_username, default_password)
                logger.info(f"Created default admin user '{default_username}' with password '{default_password}'")
                return True
            
            return False
        except PyMongoError as e:
            logger.error(f"Failed to ensure default admin: {str(e)}")
            return False

    @staticmethod
    @with_db
    def append_log(username, action, status, details=None):
        """Append a log entry to the client's logs array."""
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "status": status,
                "details": details
            }
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {"$push": {"logs": log_entry}, "$set": {"updated_at": datetime.now(timezone.utc)}}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to append log for client {username}: {str(e)}")
            return False