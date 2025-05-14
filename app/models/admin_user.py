from datetime import datetime, timezone
from .database import db, with_db, ADMIN_USERS_COLLECTION
import logging
import hashlib
import os

logger = logging.getLogger(__name__)

class AdminUser:
    """Admin user model for MongoDB.
    This model handles admin users who can access the Streamlit UI.
    """
    
    @staticmethod
    def hash_password(password, salt=None):
        """Hash a password with a salt for secure storage"""
        if salt is None:
            salt = os.urandom(32)  # Generate a random salt
        
        # Use PBKDF2 with SHA-256 (via hashlib)
        key = hashlib.pbkdf2_hmac(
            'sha256',  # Hash algorithm
            password.encode('utf-8'),  # Convert password to bytes
            salt,  # Salt
            100000,  # Number of iterations (higher is more secure but slower)
            dklen=128  # Length of the derived key
        )
        
        return salt, key
    
    @staticmethod
    def verify_password(stored_salt, stored_key, provided_password):
        """Verify a password against stored salt and key"""
        salt, key = AdminUser.hash_password(provided_password, stored_salt)
        return key == stored_key
    
    @staticmethod
    @with_db
    def create(username, password, is_active=True):
        """Create a new admin user"""
        # Check if username already exists
        existing = db[ADMIN_USERS_COLLECTION].find_one({"username": username})
        if existing:
            logger.warning(f"Username {username} already exists")
            return None
        
        # Hash the password
        salt, key = AdminUser.hash_password(password)
        
        # Create the user document
        user_doc = {
            "username": username,
            "password_salt": salt,
            "password_key": key,
            "is_active": is_active,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_login": None
        }
        
        result = db[ADMIN_USERS_COLLECTION].insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        
        logger.info(f"Admin user {username} created successfully")
        return user_doc
    
    @staticmethod
    @with_db
    def authenticate(username, password):
        """Authenticate an admin user by username and password"""
        user = db[ADMIN_USERS_COLLECTION].find_one({"username": username})
        
        if not user:
            logger.warning(f"Authentication failed: Username {username} not found")
            return None
        
        if not user.get("is_active", True):
            logger.warning(f"Authentication failed: User {username} is not active")
            return None
        
        # Verify password
        salt = user.get("password_salt")
        stored_key = user.get("password_key")
        
        if not salt or not stored_key:
            logger.error(f"Password data missing for user {username}")
            return None
        
        is_valid = AdminUser.verify_password(salt, stored_key, password)
        
        if is_valid:
            # Update last login time
            db[ADMIN_USERS_COLLECTION].update_one(
                {"_id": user["_id"]},
                {"$set": {"last_login": datetime.now(timezone.utc)}}
            )
            logger.info(f"User {username} authenticated successfully")
            return user
        else:
            logger.warning(f"Authentication failed: Invalid password for user {username}")
            return None
    
    @staticmethod
    @with_db
    def get_all():
        """Get all admin users"""
        users = db[ADMIN_USERS_COLLECTION].find({})
        return list(users)
    
    @staticmethod
    @with_db
    def get_by_username(username):
        """Get an admin user by username"""
        return db[ADMIN_USERS_COLLECTION].find_one({"username": username})
    
    @staticmethod
    @with_db
    def update_password(username, new_password):
        """Update an admin user's password"""
        user = db[ADMIN_USERS_COLLECTION].find_one({"username": username})
        if not user:
            logger.warning(f"User {username} not found")
            return False
        
        # Hash the new password
        salt, key = AdminUser.hash_password(new_password)
        
        # Update the user document
        result = db[ADMIN_USERS_COLLECTION].update_one(
            {"username": username},
            {
                "$set": {
                    "password_salt": salt,
                    "password_key": key,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        logger.info(f"Password updated for user {username}")
        return result.modified_count > 0
    
    @staticmethod
    @with_db
    def update_status(username, is_active):
        """Update an admin user's active status"""
        result = db[ADMIN_USERS_COLLECTION].update_one(
            {"username": username},
            {
                "$set": {
                    "is_active": is_active,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        status_str = "activated" if is_active else "deactivated"
        logger.info(f"User {username} {status_str}")
        return result.modified_count > 0
    
    @staticmethod
    @with_db
    def delete(username):
        """Delete an admin user"""
        result = db[ADMIN_USERS_COLLECTION].delete_one({"username": username})
        if result.deleted_count > 0:
            logger.info(f"User {username} deleted successfully")
        else:
            logger.warning(f"User {username} not found for deletion")
        return result.deleted_count > 0
    
    @staticmethod
    @with_db
    def ensure_default_admin():
        """Ensure there is at least one active admin user.
        Creates a default admin if none exists.
        """
        count = db[ADMIN_USERS_COLLECTION].count_documents({})
        
        if count == 0:
            # Create default admin
            default_username = "admin"
            default_password = "admin123"  # Should be changed immediately after first login
            
            AdminUser.create(default_username, default_password)
            logger.info(f"Created default admin user '{default_username}' with password '{default_password}'")
            return True
        
        return False 