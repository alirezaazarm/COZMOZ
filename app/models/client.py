from datetime import datetime, timezone
from .database import db, with_db
from .enums import ClientStatus, ModuleType
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
        assistant_id=None,
        vector_store_id=None,
        modules=None,
        notes=None,
        is_admin=False,
        password=None,
        email=None,
        credentials=None,
        settings=None
    ):
        """Create a new client document structure"""
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
                "assistant_id": assistant_id,
                "vector_store_id": vector_store_id,
                "password": password  # Admin password for all clients
            },
            
            # Modules (these modules don't have settings, only enabled status)
            "modules": modules or {
                "fixed_response": {
                    "enabled": True
                },
                "dm_assist": {
                    "enabled": True
                },
                "comment_assist": {
                    "enabled": True
                },
                "vision": {
                    "enabled": True
                },
                "scraper": {
                    "enabled": True
                }
            },
            
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
            }
        }
        return document

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
    def enable_module(username, module_name):
        """Enable a module for a client"""
        try:
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {
                    "$set": {
                        f"modules.{module_name}.enabled": True,
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to enable module: {str(e)}")
            return False

    @staticmethod
    @with_db
    def disable_module(username, module_name):
        """Disable a module for a client"""
        try:
            result = db[CLIENTS_COLLECTION].update_one(
                {"username": username},
                {
                    "$set": {
                        f"modules.{module_name}.enabled": False,
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to disable module: {str(e)}")
            return False

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
        """Check if a module is enabled for a client"""
        try:
            client = db[CLIENTS_COLLECTION].find_one(
                {"username": username},
                {f"modules.{module_name}": 1}
            )
            
            if not client or "modules" not in client:
                return False
                
            module = client["modules"].get(module_name, {})
            return module.get("enabled", False)
        except PyMongoError as e:
            logger.error(f"Failed to check module status: {str(e)}")
            return False

    # get_module_settings method removed - these modules don't have settings, only enabled status

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
                "modules": client.get("modules", {}),
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
                    "modules": client.get("modules", {}),
                    "last_activity": client.get("usage_stats", {}).get("last_activity"),
                    "total_users": client.get("usage_stats", {}).get("total_users", 0),
                    "enabled_modules": [
                        module for module, config in client.get("modules", {}).items()
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