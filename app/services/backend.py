import logging
from datetime import datetime, timezone
from ..models.product import Product
from ..models.post import Post
from ..config import Config
import requests
from .instagram_service import InstagramService
import importlib
from .openai_service import OpenAIService
from .img_search import process_image
from PIL import Image
import io
from ..models.additional_info import Additionalinfo
from ..models.client import Client
from ..models.story import Story
from ..models.user import User
from ..utils.exceptions import PermanentError, RetryableError

logger = logging.getLogger(__name__)

class Backend:
    def __init__(self, client_username=None):
        """
        Initialize Backend with optional client context.
        If client_username is provided, all operations will be scoped to that client.
        """
        self.client_username = client_username
        self.client_data = None
        
        # Load client data if username provided
        if self.client_username:
            self.client_data = Client.get_by_username(self.client_username)
            if not self.client_data:
                logger.error(f"Client '{self.client_username}' not found")
                raise ValueError(f"Client '{self.client_username}' not found")
            
            if self.client_data.get('status') != 'active':
                logger.error(f"Client '{self.client_username}' is not active")
                raise ValueError(f"Client '{self.client_username}' is not active")
            
            logger.info(f"Backend initialized for client: {self.client_username}")
        else:
            logger.info("Backend initialized without client context (admin mode)")
        
        self.app_setting_url = Config.BASE_URL + "/hooshang_update/app-settings"
        self.headers = {"Content-Type": "application/json",  "Authorization": f"Bearer {Config.VERIFY_TOKEN}" }
        self.scraper = self._load_scraper()
        self.openai_service = OpenAIService(client_username=self.client_username) if self.client_username else None
        
    def _load_scraper(self):
        """
        Dynamically load the scraper for the current client if it exists.
        Returns an instance of the scraper or None if not found.
        """
        if not self.client_username:
            return None
        module_name = f"app.services.scrapers.{self.client_username}"
        try:
            scraper_module = importlib.import_module(module_name)
            return scraper_module.Scraper()
        except ModuleNotFoundError:
            logger.warning(f"No scraper found for client '{self.client_username}' (module: {module_name})")
            return None
        except AttributeError:
            logger.error(f"Scraper class not found in module '{module_name}'")
            return None

    def _validate_client_access(self, required_module=None):
        """
        Validate client access and module permissions.
        Returns True if access is granted, raises exception otherwise.
        """
        if not self.client_username:
            # Admin mode - full access
            return True
            
        if not self.client_data:
            raise ValueError("Client data not loaded")
            
        if self.client_data.get('status') != 'active':
            raise ValueError(f"Client '{self.client_username}' is not active")
            
        if required_module:
            if not Client.is_module_enabled(self.client_username, required_module):
                raise ValueError(f"Module '{required_module}' is not enabled for client '{self.client_username}'")
                
        return True
        
    def _get_client_credentials(self, credential_type):
        """Get client-specific credentials"""
        if not self.client_username:
            return None
            
        return Client.get_client_credentials(self.client_username, credential_type)

    @classmethod
    def create_for_client(cls, client_username):
        """
        Factory method to create a Backend instance for a specific client.
        Validates client exists and is active before creating the instance.
        """
        try:
            return cls(client_username=client_username)
        except ValueError as e:
            logger.error(f"Failed to create Backend for client '{client_username}': {str(e)}")
            raise

    @classmethod
    def create_admin_backend(cls):
        """
        Factory method to create a Backend instance for admin operations.
        This instance has access to all clients' data.
        """
        return cls(client_username=None)

    def get_client_info(self):
        """Get information about the current client"""
        if not self.client_username:
            return None
        return self.client_data

    def get_enabled_modules(self):
        """Get list of enabled modules for the current client"""
        if not self.client_username:
            return []
        
        modules = self.client_data.get('modules', {})
        return [module for module, config in modules.items() if config.get('enabled', False)]

    def is_module_enabled(self, module_name):
        """Check if a specific module is enabled for the current client"""
        if not self.client_username:
            return True  # Admin has access to all modules
        
        return Client.is_module_enabled(self.client_username, module_name)

    # ------------------------------------------------------------------
    # Admin Authentication Methods
    # ------------------------------------------------------------------
    def authenticate_admin(self, username, password):
        """Authenticate an admin user by username and password"""
        logger.info(f"Authenticating admin user: {username}")
        try:
            user = Client.authenticate_admin(username, password)
            if user:
                logger.info(f"Admin user '{username}' authenticated successfully")
                return True
            else:
                logger.warning(f"Authentication failed for admin user '{username}'")
                return False
        except Exception as e:
            logger.error(f"Error authenticating admin user: {str(e)}")
            return False

    def create_auth_token(self, username):
        """Create a secure authentication token containing the username and expiration time"""
        logger.info(f"Creating auth token for user: {username}")
        try:
            import json
            import hmac
            import hashlib
            import base64
            import time

            # Secret key for signing - in production this should be a proper secret
            secret = Config.VERIFY_TOKEN or "streamlit_admin_secret_key"

            # Create token payload with username and expiration (7 days)
            expire_time = int(time.time()) + (7 * 24 * 60 * 60)
            token_data = {"username": username, "exp": expire_time}

            # Serialize and sign the token
            token_string = json.dumps(token_data)
            token_bytes = token_string.encode('utf-8')
            token_b64 = base64.b64encode(token_bytes).decode('utf-8')

            # Create signature
            signature = hmac.new(
                secret.encode('utf-8'),
                token_b64.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            # Return the complete token
            return f"{token_b64}.{signature}"
        except Exception as e:
            logger.error(f"Error creating auth token: {str(e)}")
            return None

    def verify_auth_token(self, token):
        """Verify the authentication token and extract the username if valid"""
        logger.info("Verifying auth token")
        try:
            import json
            import hmac
            import hashlib
            import base64
            import time

            # Secret key for verification
            secret = Config.VERIFY_TOKEN or "streamlit_admin_secret_key"

            # Split token into data and signature
            token_b64, signature = token.split('.')

            # Verify signature
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                token_b64.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            if signature != expected_signature:
                logger.warning("Token signature verification failed")
                return None

            # Decode and parse token data
            token_bytes = base64.b64decode(token_b64)
            token_data = json.loads(token_bytes.decode('utf-8'))

            # Check expiration
            if token_data.get('exp', 0) < int(time.time()):
                logger.warning("Token has expired")
                return None

            username = token_data.get('username')

            # Verify that the user exists in the database
            user = Client.get_by_username(username)
            if not user or not user.get('is_admin', False):
                logger.warning(f"Token contains invalid admin username: {username}")
                return None

            if user.get('status') != 'active':
                logger.warning(f"Token contains inactive admin user: {username}")
                return None

            logger.info(f"Token verified successfully for user: {username}")
            return username

        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return None

    def get_admin_users(self):
        """Get all admin users"""
        logger.info("Fetching all admin users")
        try:
            users = Client.get_all_admins()

            # Format user data for display
            user_data = []
            for user in users:
                username = user.get('username', 'Unknown')
                is_active = user.get('status') == 'active'
                created_at = user.get('created_at', 'Unknown')
                last_login = user.get('last_login', 'Never')

                # Format dates
                if hasattr(created_at, 'strftime'):
                    created_at = created_at.strftime("%Y-%m-%d %H:%M")
                if hasattr(last_login, 'strftime'):
                    last_login = last_login.strftime("%Y-%m-%d %H:%M")

                status = "Active" if is_active else "Inactive"
                user_data.append({
                    "Username": username,
                    "Status": status,
                    "Created": created_at,
                    "Last Login": last_login
                })

            logger.info(f"Successfully fetched {len(user_data)} admin users")
            return user_data
        except Exception as e:
            logger.error(f"Error fetching admin users: {str(e)}")
            return []

    def create_admin_user(self, username, password, is_active=True):
        """Create a new admin user"""
        logger.info(f"Creating admin user: {username}")
        try:
            result = Client.create_admin(username, password, is_active=is_active)
            if result:
                logger.info(f"Admin user '{username}' created successfully")
                return True
            else:
                logger.warning(f"Failed to create admin user '{username}'. May already exist.")
                return False
        except Exception as e:
            logger.error(f"Error creating admin user: {str(e)}")
            return False

    def update_admin_password(self, username, current_password, new_password):
        """Update an admin user's password"""
        logger.info(f"Updating password for admin user: {username}")
        try:
            # First verify the current password
            user = Client.authenticate_admin(username, current_password)
            if not user:
                logger.warning(f"Password update failed: Current password is incorrect for user '{username}'")
                return False

            # Update password
            result = Client.update_admin_password(username, new_password)
            if result:
                logger.info(f"Password updated successfully for admin user '{username}'")
                return True
            else:
                logger.warning(f"Failed to update password for admin user '{username}'")
                return False
        except Exception as e:
            logger.error(f"Error updating admin user password: {str(e)}")
            return False

    def update_admin_status(self, username, is_active):
        """Update an admin user's active status"""
        logger.info(f"Updating status for admin user: {username} to {'active' if is_active else 'inactive'}")
        try:
            result = Client.update_admin_status(username, is_active)
            if result:
                logger.info(f"Status updated successfully for admin user '{username}'")
                return True
            else:
                logger.warning(f"Failed to update status for admin user '{username}'")
                return False
        except Exception as e:
            logger.error(f"Error updating admin user status: {str(e)}")
            return False

    def delete_admin_user(self, username):
        """Delete an admin user"""
        logger.info(f"Deleting admin user: {username}")
        try:
            result = Client.delete_admin(username)
            if result:
                logger.info(f"Admin user '{username}' deleted successfully")
                return True
            else:
                logger.warning(f"Failed to delete admin user '{username}'")
                return False
        except Exception as e:
            logger.error(f"Error deleting admin user: {str(e)}")
            return False

    def ensure_default_admin(self):
        """Ensure there is at least one active admin user"""
        logger.info("Checking for default admin user")
        try:
            result = Client.ensure_default_admin()
            if result:
                logger.info("Default admin user created")
            else:
                logger.info("Default admin user already exists")
            return True
        except Exception as e:
            logger.error(f"Error ensuring default admin: {str(e)}")
            return False

    @staticmethod
    def format_updated_at(updated_at):
        logger.debug(f"Formatting updated_at timestamp: {updated_at}.")
        if not updated_at:
            logger.debug("Timestamp is empty or None.")
            return "Never updated"

        try:
            # Handle timestamps without timezone info (assume UTC)
            updated_time = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)

            # Calculate time difference
            time_diff = datetime.now(timezone.utc) - updated_time
            days = time_diff.days
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes = remainder // 60

            if days > 0:
                return f"{days} day{'s' if days > 1 else ''}, {hours} hour{'s' if hours > 1 else ''} ago"
            elif hours > 0:
                return f"{hours} hour{'s' if hours > 1 else ''}, {minutes} minute{'s' if minutes > 1 else ''} ago"
            else:
                return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        except ValueError as e:
            logger.error(f"Invalid timestamp format: {updated_at}. Error: {str(e)}")
            return "Invalid timestamp"

    # ------------------------------------------------------------------
    # Appsetting  ---> main app (now client-centric)
    # ------------------------------------------------------------------
    def reload_main_app_memory(self):
        """Trigger the main app to reload all memory from the database."""
        logger.info("Triggering main app to reload memory from DB.")
        try:
            response = requests.post(
                Config.BASE_URL + "/hooshang_update/reload-memory",
                headers=self.headers
            )
            if response.status_code == 200:
                logger.info("Main app memory reload triggered successfully.")
                return True
            else:
                logger.error(f"Failed to trigger main app memory reload. Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error triggering main app memory reload: {str(e)}")
            return False

    def get_app_setting(self, key):
        logger.info(f"Fetching app setting for key: {key} (from client model).")
        try:
            if not self.client_username or not self.client_data:
                logger.warning("No client context loaded for app settings.")
                return None
            # Map key to client model fields
            if key == 'vs_id':
                return self.client_data.get('keys', {}).get('vector_store_id')
            elif key == 'assistant':
                return self.client_data.get('modules', {}).get('dm_assist', {}).get('enabled', False)
            elif key == 'fixed_responses':
                return self.client_data.get('modules', {}).get('fixed_response', {}).get('enabled', False)
            # Add more mappings as needed
            else:
                logger.warning(f"Unknown app setting key requested: {key}")
                return None
        except Exception as e:
            logger.error(f"Error in get_app_setting for key '{key}': {str(e)}")
            return {"error in get_app_setting calling": str(e)}

    def update_is_active(self, key, value):
        logger.info(f"Updating client app setting for key: {key} with value: {value}.")
        def _to_bool(val):
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() == "true"
            return bool(val)
        try:
            if not self.client_username:
                logger.error("No client context loaded for update_is_active.")
                return False
            update_data = {}
            if key == 'assistant':
                update_data = {f"modules.dm_assist.enabled": _to_bool(value)}
            elif key == 'fixed_responses':
                update_data = {f"modules.fixed_response.enabled": _to_bool(value)}
            elif key == 'vs_id':
                update_data = {f"keys.vector_store_id": value}
            else:
                logger.warning(f"Unknown app setting key for update: {key}")
                return False
            result = Client.update(self.client_username, update_data)
            if result:
                logger.info(f"Client app setting updated for key: {key}.")
                # Refresh local client_data
                self.client_data = Client.get_by_username(self.client_username)
            else:
                logger.error(f"Failed to update client app setting for key: {key}.")
            self.reload_main_app_memory()
        except Exception as e:
            logger.error(f"Error in update_is_active for key '{key}': {str(e)}")
            return {"error in update_is_active": str(e)}

    # ------------------------------------------------------------------
    # Client dashboard ---> main app memory update
    # ------------------------------------------------------------------
    def get_post_fixed_responses(self, post_id): # Renamed
        """Get fixed responses for a post for the current client"""
        self._validate_client_access('fixed_response')
        logger.info(f"Fetching fixed responses for post ID: {post_id} for client: {self.client_username or 'admin'}")
        try:
            responses = Post.get_fixed_responses(post_id, client_username=self.client_username) # Use the new model method
            if responses: 
                logger.info(f"Fixed responses found for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return responses
            else: 
                logger.info(f"No fixed responses found for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return []
        except Exception as e: 
            logger.error(f"Error fetching fixed responses for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return []

    def create_or_update_post_fixed_response(self, post_id, trigger_keyword, comment_response_text=None, direct_response_text=None): # Renamed
        """Create or update fixed response for a post for the current client"""
        self._validate_client_access('fixed_response')
        logger.info(f"Adding/updating fixed response for post ID: {post_id} with trigger: {trigger_keyword} for client: {self.client_username or 'admin'}")
        try:
            # Use the model method
            result = Post.add_fixed_response(post_id, trigger_keyword, self.client_username, comment_response_text, direct_response_text)
            self.reload_main_app_memory()
            if result: 
                logger.info(f"Fixed response added/updated successful for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else: 
                logger.warning(f"Failed to add/update fixed response for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e: 
            logger.error(f"Error adding/updating fixed response for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return False

    def delete_post_fixed_response(self, post_id, trigger_keyword): # Modified to accept trigger_keyword
        """Delete fixed response for a post for the current client"""
        self._validate_client_access('fixed_response')
        logger.info(f"Deleting fixed response for post ID: {post_id} with trigger: {trigger_keyword} for client: {self.client_username or 'admin'}")
        try:
            result = Post.delete_fixed_response(post_id, trigger_keyword, client_username=self.client_username) # Use the model method with trigger
            self.reload_main_app_memory()
            if result: 
                logger.info(f"Fixed response deleted successfully for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else: 
                logger.warning(f"Failed to delete fixed response for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e: 
            logger.error(f"Error deleting fixed response for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return False

    def set_post_admin_explanation(self, post_id, explanation):
        """Set admin explanation for a post for the current client"""
        self._validate_client_access()
        logger.info(f"Setting admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
        try:
            result = Post.set_admin_explanation(post_id, explanation, client_username=self.client_username) # Use the model method
            if result: 
                logger.info(f"Admin explanation set for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else: 
                logger.warning(f"Failed to set admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e: 
            logger.error(f"Error setting admin explanation for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return False

    def get_post_admin_explanation(self, post_id):
        """Get admin explanation for a post for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
        try:
            explanation = Post.get_admin_explanation(post_id, client_username=self.client_username) # Use the model method
            if explanation is not None: 
                logger.info(f"Admin explanation found for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return explanation
            else: 
                logger.info(f"No admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return None # Distinguish empty from not found
        except Exception as e: 
            logger.error(f"Error fetching admin explanation for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return None

    def remove_post_admin_explanation(self, post_id):
        """Remove admin explanation for a post for the current client"""
        self._validate_client_access()
        logger.info(f"Removing admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
        try:
            result = Post.remove_admin_explanation(post_id, client_username=self.client_username) # Use the model method
            if result: 
                logger.info(f"Admin explanation removed for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else: 
                logger.warning(f"Failed to remove admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e: 
            logger.error(f"Error removing admin explanation for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return False

    # ------------------------------------------------------------------
    # Data : Product + additional info
    # ------------------------------------------------------------------
    def update_products(self):
        """Update products for the current client"""
        self._validate_client_access('scraper')
        logger.info(f"Scraping the site is starting for client: {self.client_username or 'admin'}")
        try:
            self.scraper.update_products()
            logger.info("Update products completed.")
        except Exception as e:
            logger.error(f"Failed to update products: {str(e)}", exc_info=True)
            return False

        try:
            self.reload_main_app_memory()
        except Exception as e:
            logger.error(f"Failed to send app settings: {e}")

        return True

    def get_products(self):
        """Get products for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching products from the database for client: {self.client_username or 'admin'}")
        try:
            # Use the MongoDB Product model directly with client filtering
            products = Product.get_all(client_username=self.client_username)
            products_data = [
                {
                    "Title": p['title'],
                    "Price": p['price'] if isinstance(p['price'], dict) else p['price'],
                    "Additional info": p['additional_info'] if isinstance(p['additional_info'], dict) else p['additional_info'],
                    "Category": p['category'],
                    "Stock status": p['stock_status'],
                    "Link": p['link']
                }
                for p in products
            ]
            logger.info(f"Successfully fetched {len(products_data)} products for client: {self.client_username or 'admin'}")
            return products_data
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return []

    def get_additionalinfo(self, content_format="markdown"):
        """Return all additional text entries as a list of dicts with 'key' and 'value' for the current client."""
        self._validate_client_access()
        try:
            # Default to markdown format if no format specified
            entries = Additionalinfo.get_by_format(content_format, client_username=self.client_username)
            
            result = []
            for entry in entries:
                item = {
                    "id": str(entry["_id"]),
                    "key": entry["title"], 
                    "value": entry["content"],
                    "content_format": entry.get("content_format", "markdown")
                }
                result.append(item)
            return result
        except Exception as e:
            logger.error(f"Error fetching additional text entries: {str(e)}")
            return []

    def add_additionalinfo(self, key, value, content_format="markdown"):
        """Add or update a text entry in the additional_text collection with the given key and value for the current client."""
        self._validate_client_access()
        logger.info(f"Adding/updating additional text: {key} for client: {self.client_username or 'admin'}")
        try:
            # Check if an entry with this title already exists for this client
            existing = Additionalinfo.search(key, client_username=self.client_username)
            if existing and len(existing) > 0:
                # Update existing entry
                result = Additionalinfo.update(str(existing[0]['_id']), {
                    "title": key,
                    "content": value,
                    "content_format": content_format,
                    "client_username": self.client_username
                })
            else:
                # Create new entry
                result = Additionalinfo.create(title=key, content=value, client_username=self.client_username, content_format=content_format)

            if result:
                logger.info(f"Additional text '{key}' created/updated successfully for client: {self.client_username or 'admin'}")
                return True
            else:
                logger.error(f"Failed to create/update additional text '{key}'.")
                return False
        except Exception as e:
            logger.error(f"Error creating/updating additional text '{key}': {str(e)}")
            return False

    def get_additionalinfo_json(self):
        """Return all JSON format additional text entries for the current client."""
        self._validate_client_access()
        try:
            entries = Additionalinfo.get_by_format("json", client_username=self.client_username)
            result = []
            for entry in entries:
                # Parse JSON content into key-value pairs
                json_data = Additionalinfo.parse_json_content(entry["content"])
                item = {
                    "id": str(entry["_id"]),
                    "title": entry["title"],
                    "json_data": json_data,
                    "content": entry["content"]
                }
                result.append(item)
            return result
        except Exception as e:
            logger.error(f"Error fetching JSON additional text entries: {str(e)}")
            return []

    def add_additionalinfo_json(self, title, key_value_pairs):
        """Add or update a JSON format additional text entry for the current client."""
        self._validate_client_access()
        logger.info(f"Adding/updating JSON additional text: {title} for client: {self.client_username or 'admin'}")
        try:
            # Convert key-value pairs to JSON content
            json_content = Additionalinfo.create_json_content(key_value_pairs)
            
            # Check if an entry with this title already exists for this client
            existing = Additionalinfo.search(title, client_username=self.client_username)
            if existing and len(existing) > 0:
                # Update existing entry
                result = Additionalinfo.update(str(existing[0]['_id']), {
                    "title": title,
                    "content": json_content,
                    "content_format": "json",
                    "client_username": self.client_username
                })
            else:
                # Create new entry
                result = Additionalinfo.create(title=title, content=json_content, client_username=self.client_username, content_format="json")

            if result:
                logger.info(f"JSON additional text '{title}' created/updated successfully for client: {self.client_username or 'admin'}")
                return True
            else:
                logger.error(f"Failed to create/update JSON additional text '{title}'.")
                return False
        except Exception as e:
            logger.error(f"Error creating/updating JSON additional text '{title}': {str(e)}")
            return False

    def update_additionalinfo_json_by_id(self, entry_id, title, key_value_pairs):
        """Update a JSON format additional text entry by ID for the current client."""
        self._validate_client_access()
        logger.info(f"Updating JSON additional text ID: {entry_id} for client: {self.client_username or 'admin'}")
        try:
            # Convert key-value pairs to JSON content
            json_content = Additionalinfo.create_json_content(key_value_pairs)
            
            # Update entry by ID
            result = Additionalinfo.update(entry_id, {
                "title": title,
                "content": json_content,
                "content_format": "json",
                "client_username": self.client_username
            }, client_username=self.client_username)

            if result:
                logger.info(f"JSON additional text ID '{entry_id}' updated successfully for client: {self.client_username or 'admin'}")
                return True
            else:
                logger.error(f"Failed to update JSON additional text ID '{entry_id}'.")
                return False
        except Exception as e:
            logger.error(f"Error updating JSON additional text ID '{entry_id}': {str(e)}")
            return False

    def delete_additionalinfo_by_id(self, entry_id):
        """Delete an additional text entry by ID for the current client."""
        self._validate_client_access()
        logger.info(f"Deleting additional text ID: {entry_id} for client: {self.client_username or 'admin'}")
        try:
            # Get the entry first to check if it has a file_id
            entry = Additionalinfo.get_by_id(entry_id, client_username=self.client_username)
            if not entry:
                logger.error(f"Additional text entry with ID '{entry_id}' not found for client: {self.client_username or 'admin'}")
                return False

            # Delete file from openai if it has file_id
            if entry.get('file_id'):
                if not self.openai_service:
                    logger.error("OpenAI service not initialized")
                    return False
                resp = self.openai_service.delete_single_file(entry['file_id'])
                if resp:
                    result = Additionalinfo.delete(entry_id, client_username=self.client_username)
                    if result:
                        logger.info(f"Additional text ID '{entry_id}' deleted from DB successfully for client: {self.client_username or 'admin'}")
                        return True
                    else:
                        logger.error(f"Failed to delete additional text ID '{entry_id}' from DB.")
                        return False
                else:
                    logger.error(f"Failed to delete file '{entry['file_id']}' from openai.")
                    return False
            else:
                result = Additionalinfo.delete(entry_id, client_username=self.client_username)
                if result:
                    logger.info(f"Additional text ID '{entry_id}' deleted from DB successfully for client: {self.client_username or 'admin'}")
                    return True
                else:
                    logger.error(f"Failed to delete additional text ID '{entry_id}' from DB.")
                    return False

        except Exception as e:
            logger.error(f"Error deleting additional text entry ID '{entry_id}': {str(e)}")
            return False

    def delete_additionalinfo(self, key):
        """Delete an additional text entry by title for the current client."""
        self._validate_client_access()
        try:
            # Find the entry with the matching title for this client
            entries = Additionalinfo.search(key, client_username=self.client_username)
            if not entries or len(entries) == 0:
                logger.error(f"Additional text entry with title '{key}' not found for client: {self.client_username or 'admin'}")
                return False

            # delete file from openai if it has file_id
            if entries[0].get('file_id'):
                if not self.openai_service:
                    logger.error("OpenAI service not initialized")
                    return False
                resp = self.openai_service.delete_single_file(entries[0]['file_id'])
                if resp:
                    result = Additionalinfo.delete(str(entries[0]['_id']))
                    if result:
                        logger.info(f"Additional text title '{key}' deleted from DB successfully for client: {self.client_username or 'admin'}")
                        return True
                    else:
                        logger.error(f"Failed to delete additional text title '{key}' from DB.")
                        return False
                else:
                    logger.error(f"Failed to delete file '{entries[0]['file_id']}' from openai.")
                    return False
            else:
                result = Additionalinfo.delete(str(entries[0]['_id']))
                if result:
                    logger.info(f"Additional text title '{key}' deleted from DB successfully for client: {self.client_username or 'admin'}")
                    return True
                else:
                    logger.error(f"Failed to delete additional text title '{key}' from DB.")
                    return False

        except Exception as e:
            logger.error(f"Error deleting additional text entry '{key}': {str(e)}")
            return False

    def rebuild_files_and_vs(self):
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                return False
            
            scraper_update_products_success = self.update_products()
            if scraper_update_products_success:
                logger.info("Scraper successfully scraped the website")
                clear_success = self.openai_service.rebuild_all()
                if clear_success:
                    logger.info("Additional info + products files and vector store rebuilt successfully")
                    return True
                else:
                    logger.error("Failed to rebuild additional info files and vector store")
                    return False
            else:
                logger.error("the Sraper Failed to scrape the website")
                return False
            
        except Exception as e:
            logger.error(f"Error in update_additionalinfo_files_and_vs: {str(e)}")
            return False

    # ------------------------------------------------------------------
    # Instagram management : Posts + Stories + vision
    # ------------------------------------------------------------------
    # --- Vision ---
    def _process_media_for_labeling(self, item_id, media_url, thumbnail_url, item_type="post"):
        """Helper to download and process an image for labeling."""
        if not media_url and not thumbnail_url:
            logger.warning(f"{item_type.capitalize()} ID {item_id} has no media URL or thumbnail URL.")
            return None, "No image URL available"

        url_to_use = thumbnail_url if thumbnail_url else media_url
        logger.info(f"Downloading image for {item_type} ID {item_id} from {url_to_use}")

        try:
            response = requests.get(url_to_use, stream=True, timeout=20)
            response.raise_for_status()
            image_bytes = response.content
            if not image_bytes:
                return None, "Downloaded image is empty"

            image_stream = io.BytesIO(image_bytes)
            pil_image = Image.open(image_stream)
            predicted_label = process_image(pil_image, self.client_username) # Assumes process_image returns label or None

            if not predicted_label:
                logger.info(f"Vision model couldn't find a label for {item_type} ID {item_id}")
                return None, "Model couldn't determine a label"
            return predicted_label, None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download image for {item_type} {item_id}: {str(e)}")
            return None, f"Failed to download image: {str(e)}"
        except Image.UnidentifiedImageError:
            logger.error(f"Could not identify image for {item_type} {item_id} (not a valid image format or corrupted). URL: {url_to_use}")
            return None, "Invalid image format or corrupted file."
        except Exception as e:
            logger.error(f"Error processing image for {item_type} {item_id}: {str(e)}")
            return None, f"Error processing image: {str(e)}"

    # --- Post Methods ---
    def fetch_instagram_posts(self):
        """Fetch Instagram posts for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching Instagram posts for client: {self.client_username or 'admin'}")
        try:
            result = InstagramService.get_posts(client_username=self.client_username)
            if result:
                self.reload_main_app_memory()
                logger.info(f"Instagram posts fetched/updated successfully for client: {self.client_username or 'admin'}")
            else: 
                logger.warning(f"Failed to fetch/update Instagram posts for client: {self.client_username or 'admin'}")
            return result
        except Exception as e: 
            logger.error(f"Failed to fetch Instagram posts for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return False

    def get_posts(self):
        """Get stored Instagram posts for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching stored Instagram posts for client: {self.client_username or 'admin'}")
        try:
            posts = Post.get_all(client_username=self.client_username)
            post_data = [
                {"id": post.get('id'), "media_url": post.get('media_url'), "thumbnail_url": post.get('thumbnail_url'),
                 "caption": post.get('caption'), "label": post.get('label', ''), "media_type": post.get('media_type')}
                for post in posts if post.get('id') # Ensure id exists
            ]
            logger.info(f"Successfully fetched {len(post_data)} Instagram posts for client: {self.client_username or 'admin'}")
            return post_data
        except Exception as e: 
            logger.error(f"Error fetching stored Instagram posts for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return []

    def set_post_label(self, post_id, label):
        """Set label for a post for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Setting label '{label}' for post ID: {post_id} for client: {self.client_username or 'admin'}")
        if not post_id: 
            logger.error("Cannot set post label: post_id is missing.")
            return False
        try:
            success = Post.set_label(post_id, label, client_username=self.client_username)
            if success: 
                logger.info(f"Label update successful for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else: 
                logger.warning(f"Could not set label for post ID {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e: 
            logger.error(f"Error setting label for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return False

    def remove_post_label(self, post_id):
        """Remove label for a post for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Removing label for post ID: {post_id} for client: {self.client_username or 'admin'}")
        if not post_id: 
            logger.error("Cannot remove post label: post_id is missing.")
            return False
        try:
            success = Post.remove_label(post_id, client_username=self.client_username) # This sets label to ""
            if success: 
                logger.info(f"Label removed for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else: 
                logger.warning(f"Could not remove label for post ID {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e: 
            logger.error(f"Error removing label for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return False

    def unset_all_post_labels(self):
        """Unset labels from all posts for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Unsetting labels from all posts for client: {self.client_username or 'admin'}")
        try:
            updated_count = Post.unset_all_labels(client_username=self.client_username)
            logger.info(f"Successfully unset labels from {updated_count} posts for client: {self.client_username or 'admin'}")
            return updated_count
        except Exception as e: 
            logger.error(f"Error unsetting all post labels for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return 0

    def set_single_post_label_by_model(self, post_id):
        """Set label for a single post using AI model for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Processing post ID {post_id} for automatic labeling for client: {self.client_username or 'admin'}")
        try:
            post = Post.get_by_instagram_id(post_id, client_username=self.client_username)
            if not post:
                logger.warning(f"Post with ID {post_id} not found for client: {self.client_username or 'admin'}")
                return {"success": False, "message": "Post not found"}

            predicted_label, error_msg = self._process_media_for_labeling(post_id, post.get('media_url'), post.get('thumbnail_url'), "post")
            if error_msg:
                return {"success": False, "message": error_msg}

            if predicted_label:
                label_set_success = self.set_post_label(post_id, predicted_label)
                if label_set_success:
                    logger.info(f"Post ID {post_id} automatically labeled as '{predicted_label}' for client: {self.client_username or 'admin'}")
                    return {"success": True, "label": predicted_label}
                else:
                    return {"success": False, "message": "Failed to set label in database"}
            return {"success": False, "message": "Model couldn't determine a label"} # Should be caught by _process_media_for_labeling

        except Exception as e:
            logger.error(f"Error in set_single_post_label_by_model for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def set_post_labels_by_model(self):
        """Set labels for all unlabeled posts using AI model for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Starting automatic labeling of posts by model for client: {self.client_username or 'admin'}")
        processed_count, labeled_count, errors = 0, 0, []
        all_posts = Post.get_all(client_username=self.client_username)
        if not all_posts:
            return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'No posts found.'}

        unlabeled_posts = [p for p in all_posts if not p.get('label')]
        logger.info(f"Found {len(unlabeled_posts)} posts without labels for client: {self.client_username or 'admin'}")
        if not unlabeled_posts:
            return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'All posts are already labeled.'}

        for post in unlabeled_posts:
            post_id = post.get('id')
            processed_count += 1
            if not post_id: errors.append(f"Post missing Instagram ID: MongoDB _id {post.get('_id', 'N/A')}"); continue

            predicted_label, error_msg = self._process_media_for_labeling(post_id, post.get('media_url'), post.get('thumbnail_url'), "post")
            if error_msg:
                errors.append(f"Post ID {post_id}: {error_msg}"); continue

            if predicted_label:
                if self.set_post_label(post_id, predicted_label): labeled_count += 1
                else: errors.append(f"Failed to set label for post ID {post_id} after prediction '{predicted_label}'.")

        message = f"Processed {processed_count} unlabeled posts. Set labels for {labeled_count} posts for client: {self.client_username or 'admin'}"
        if errors: message += f" Encountered {len(errors)} errors. First few: {'; '.join(errors[:3])}"
        logger.info(message)
        return {'success': not errors, 'processed': processed_count, 'labeled': labeled_count, 'message': message, 'errors': errors}

    def download_post_labels(self):
        """Prepare posts organized by labels for download for the current client"""
        self._validate_client_access()
        logger.info(f"Preparing posts organized by labels for download for client: {self.client_username or 'admin'}")
        try:
            posts = Post.get_all(client_username=self.client_username)
            if not posts: return {}
            labeled_posts = {}
            for post in posts:
                label = post.get('label', '').strip()
                if not label: continue # Skip unlabeled or empty-label posts
                
                # Add main post URL (prefer thumbnail_url over media_url)
                image_url = post.get('thumbnail_url') or post.get('media_url')
                if image_url:
                    if label not in labeled_posts: labeled_posts[label] = []
                    labeled_posts[label].append(image_url)
                
                # Add children URLs if they exist (prefer thumbnail_url over media_url for each child)
                children = post.get('children', [])
                if children:
                    for child in children:
                        child_url = child.get('thumbnail_url') or child.get('media_url')
                        if child_url:
                            if label not in labeled_posts: labeled_posts[label] = []
                            labeled_posts[label].append(child_url)
                            
            logger.info(f"Successfully prepared posts by label, found {len(labeled_posts)} unique labels for client: {self.client_username or 'admin'}")
            return labeled_posts
        except Exception as e: logger.error(f"Error preparing post labels for download: {str(e)}", exc_info=True); return {"error": str(e)}

    # --- Story Methods (Paired with Post Methods) ---
    def fetch_instagram_stories(self):
        """Fetch Instagram stories for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching Instagram stories for client: {self.client_username or 'admin'}")
        try:
            # InstagramService.get_stories should ideally call Story.create_or_update_from_instagram
            result = InstagramService.get_stories(client_username=self.client_username)
            if result:
                logger.info(f"Instagram stories fetched/updated successfully for client: {self.client_username or 'admin'}")
                self.reload_main_app_memory()
            else: 
                logger.warning(f"Failed to fetch/update Instagram stories for client: {self.client_username or 'admin'}")
            return result
        except Exception as e: 
            logger.error(f"Failed to fetch Instagram stories for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return False

    def get_stories(self):
        """Get stored Instagram stories for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching stored Instagram stories for client: {self.client_username or 'admin'}")
        try:
            stories = Story.get_all(client_username=self.client_username) # Fetches from DB
            story_data = [
                {"id": story.get('id'), "media_url": story.get('media_url'), "thumbnail_url": story.get('thumbnail_url'),
                 "caption": story.get('caption'), "label": story.get('label', ''), "media_type": story.get('media_type')}
                for story in stories if story.get('id') # Ensure id exists
            ]
            logger.info(f"Successfully fetched {len(story_data)} Instagram stories from DB for client: {self.client_username or 'admin'}")
            return story_data
        except Exception as e: 
            logger.error(f"Error fetching stored Instagram stories for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return []

    def set_story_label(self, story_id, label):
        """Set label for a story for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Setting label '{label}' for story ID: {story_id} for client: {self.client_username or 'admin'}")
        if not story_id: logger.error("Cannot set story label: story_id is missing."); return False
        try:
            success = Story.set_label(story_id, label, client_username=self.client_username)
            if success: logger.info(f"Label update successful for story ID: {story_id}"); return True
            else: logger.warning(f"Could not set label for story ID {story_id}"); return False
        except Exception as e: logger.error(f"Error setting label for story ID {story_id}: {str(e)}", exc_info=True); return False

    def remove_story_label(self, story_id):
        """Remove label for a story for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Removing label for story ID: {story_id} for client: {self.client_username or 'admin'}")
        if not story_id: logger.error("Cannot remove story label: story_id is missing."); return False
        try:
            success = Story.remove_label(story_id, client_username=self.client_username)
            if success: logger.info(f"Label removed for story ID: {story_id}"); return True
            else: logger.warning(f"Could not remove label for story ID {story_id}"); return False
        except Exception as e: logger.error(f"Error removing label for story ID {story_id}: {str(e)}", exc_info=True); return False

    def unset_all_story_labels(self):
        """Unset labels from all stories for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Unsetting labels from all stories for client: {self.client_username or 'admin'}")
        try:
            updated_count = Story.unset_all_labels(client_username=self.client_username)
            logger.info(f"Successfully unset labels from {updated_count} stories for client: {self.client_username or 'admin'}")
            return updated_count
        except Exception as e: logger.error(f"Error unsetting all story labels: {str(e)}", exc_info=True); return 0

    def set_single_story_label_by_model(self, story_id):
        """Set label for a single story using AI model for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Processing story ID {story_id} for automatic labeling for client: {self.client_username or 'admin'}")
        try:
            story = Story.get_by_instagram_id(story_id, client_username=self.client_username)
            if not story:
                logger.warning(f"Story with ID {story_id} not found."); return {"success": False, "message": "Story not found"}

            # Stories can be videos. process_image expects an image.
            # Simplified: only attempt if media_type is IMAGE or if thumbnail_url exists.
            media_type = story.get('media_type', '').upper()
            media_url = story.get('media_url')
            thumbnail_url = story.get('thumbnail_url')

            if media_type == 'VIDEO' and not thumbnail_url:
                logger.info(f"Story ID {story_id} is a video without a thumbnail. Skipping AI labeling.")
                return {"success": False, "message": "Cannot label video without thumbnail."}

            predicted_label, error_msg = self._process_media_for_labeling(story_id, media_url, thumbnail_url, "story")
            if error_msg:
                return {"success": False, "message": error_msg}

            if predicted_label:
                label_set_success = self.set_story_label(story_id, predicted_label)
                if label_set_success:
                    logger.info(f"Story ID {story_id} automatically labeled as '{predicted_label}'")
                    return {"success": True, "label": predicted_label}
                else:
                    return {"success": False, "message": "Failed to set label in database"}
            return {"success": False, "message": "Model couldn't determine a label"}

        except Exception as e:
            logger.error(f"Error in set_single_story_label_by_model for story ID {story_id}: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def set_story_labels_by_model(self):
        """Set labels for all unlabeled stories using AI model for the current client"""
        self._validate_client_access('vision')
        logger.info(f"Starting automatic labeling of stories by model for client: {self.client_username or 'admin'}")
        processed_count, labeled_count, errors = 0, 0, []
        all_stories = Story.get_all(client_username=self.client_username)
        if not all_stories:
            return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'No stories found.'}

        unlabeled_stories = [s for s in all_stories if not s.get('label')]
        logger.info(f"Found {len(unlabeled_stories)} stories without labels for client: {self.client_username or 'admin'}")
        if not unlabeled_stories:
            return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'All stories are already labeled.'}

        for story in unlabeled_stories:
            story_id = story.get('id')
            processed_count += 1
            if not story_id: errors.append(f"Story missing Instagram ID: MongoDB _id {story.get('_id', 'N/A')}"); continue

            media_type = story.get('media_type', '').upper()
            media_url = story.get('media_url')
            thumbnail_url = story.get('thumbnail_url')

            if media_type == 'VIDEO' and not thumbnail_url:
                errors.append(f"Story ID {story_id}: Cannot label video without thumbnail."); continue

            predicted_label, error_msg = self._process_media_for_labeling(story_id, media_url, thumbnail_url, "story")
            if error_msg:
                errors.append(f"Story ID {story_id}: {error_msg}"); continue

            if predicted_label:
                if self.set_story_label(story_id, predicted_label): labeled_count += 1
                else: errors.append(f"Failed to set label for story ID {story_id} after prediction '{predicted_label}'.")

        message = f"Processed {processed_count} unlabeled stories. Set labels for {labeled_count} stories for client: {self.client_username or 'admin'}"
        if errors: message += f" Encountered {len(errors)} errors. First few: {'; '.join(errors[:3])}"
        logger.info(message)
        return {'success': not errors, 'processed': processed_count, 'labeled': labeled_count, 'message': message, 'errors': errors}

    def download_story_labels(self):
        """Prepare stories organized by labels for download for the current client"""
        self._validate_client_access()
        logger.info(f"Preparing stories organized by labels for download for client: {self.client_username or 'admin'}")
        try:
            stories = Story.get_all(client_username=self.client_username)
            if not stories: return {}
            labeled_stories = {}
            for story in stories:
                label = story.get('label', '').strip()
                if not label: continue
                image_url = story.get('thumbnail_url') or story.get('media_url') # Prefer thumbnail
                if not image_url: continue
                if label not in labeled_stories: labeled_stories[label] = []
                labeled_stories[label].append(image_url)
            logger.info(f"Successfully prepared stories by label, found {len(labeled_stories)} unique labels for client: {self.client_username or 'admin'}")
            return labeled_stories
        except Exception as e: logger.error(f"Error preparing story labels for download: {str(e)}", exc_info=True); return {"error": str(e)}

    def get_story_fixed_responses(self, story_id): # Renamed
        """Get fixed responses for a story for the current client"""
        self._validate_client_access('fixed_response')
        logger.info(f"Fetching fixed responses for story ID: {story_id} for client: {self.client_username or 'admin'}")
        try:
            responses = Story.get_fixed_responses(story_id, client_username=self.client_username) # Use the new model method
            if responses: logger.info(f"Fixed responses found for story ID: {story_id}"); return responses
            else: logger.info(f"No fixed responses found for story ID: {story_id}"); return []
        except Exception as e: logger.error(f"Error fetching fixed responses for story ID {story_id}: {str(e)}"); return []

    def create_or_update_story_fixed_response(self, story_id, trigger_keyword, direct_response_text=None):
        """Create or update fixed response for a story for the current client"""
        self._validate_client_access('fixed_response')
        logger.info(f"Adding/updating fixed response for story ID: {story_id} with trigger: {trigger_keyword} for client: {self.client_username or 'admin'}")
        try:
            # Use the model method. Note: No comment_response_text for stories.
            result = Story.add_fixed_response(
                story_id,
                trigger_keyword,
                client_username=self.client_username,
                direct_response_text=direct_response_text
            )
            self.reload_main_app_memory()
            if result: logger.info(f"Fixed response added/updated successful for story ID: {story_id}"); return True
            else: logger.warning(f"Failed to add/update fixed response for story ID: {story_id}"); return False
        except Exception as e: logger.error(f"Error adding/updating fixed response for story ID {story_id}: {str(e)}"); return False

    def delete_story_fixed_response(self, story_id, trigger_keyword):
        """Delete fixed response for a story for the current client"""
        self._validate_client_access('fixed_response')
        logger.info(f"Deleting fixed response for story ID: {story_id} with trigger: {trigger_keyword} for client: {self.client_username or 'admin'}")
        try:
            result = Story.delete_fixed_response(story_id, trigger_keyword, client_username=self.client_username) # Use the model method with trigger
            self.reload_main_app_memory()
            if result: logger.info(f"Fixed response deleted successfully for story ID: {story_id}"); return True
            else: logger.warning(f"Failed to delete fixed response for story ID: {story_id}"); return False
        except Exception as e: logger.error(f"Error deleting fixed response for story ID {story_id}: {str(e)}"); return False

    def set_story_admin_explanation(self, story_id, explanation):
        """Set admin explanation for a story for the current client"""
        self._validate_client_access()
        logger.info(f"Setting admin explanation for story ID: {story_id} for client: {self.client_username or 'admin'}")
        try:
            result = Story.set_admin_explanation(story_id, explanation, client_username=self.client_username) # Use the model method
            if result: logger.info(f"Admin explanation set for story ID: {story_id}"); return True
            else: logger.warning(f"Failed to set admin explanation for story ID: {story_id}"); return False
        except Exception as e: logger.error(f"Error setting admin explanation for story ID {story_id}: {str(e)}"); return False

    def get_story_admin_explanation(self, story_id):
        """Get admin explanation for a story for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching admin explanation for story ID: {story_id} for client: {self.client_username or 'admin'}")
        try:
            explanation = Story.get_admin_explanation(story_id, client_username=self.client_username) # Use the model method
            if explanation is not None: logger.info(f"Admin explanation found for story ID: {story_id}"); return explanation
            else: logger.info(f"No admin explanation for story ID: {story_id}"); return None
        except Exception as e: logger.error(f"Error fetching admin explanation for story ID {story_id}: {str(e)}"); return None

    def remove_story_admin_explanation(self, story_id):
        """Remove admin explanation for a story for the current client"""
        self._validate_client_access()
        logger.info(f"Removing admin explanation for story ID: {story_id} for client: {self.client_username or 'admin'}")
        try:
            result = Story.remove_admin_explanation(story_id, client_username=self.client_username) # Use the model method
            if result: logger.info(f"Admin explanation removed for story ID: {story_id}"); return True
            else: logger.warning(f"Failed to remove admin explanation for story ID: {story_id}"); return False
        except Exception as e: logger.error(f"Error removing admin explanation for story ID {story_id}: {str(e)}"); return False

    # ------------------------------------------------------------------
    # Openai management
    # ------------------------------------------------------------------
    def get_vs_id(self):
        """Get the vector store ID from the client model."""
        logger.info("Fetching current vector store ID from client model.")
        try:
            if not self.client_username or not self.client_data:
                logger.warning("No client context loaded for get_vs_id.")
                return None
            vs_id = self.client_data.get('keys', {}).get('vector_store_id')
            if vs_id:
                logger.info(f"Current vector store ID: {vs_id}")
                return [vs_id]
            else:
                logger.info("No vector store ID found in client model.")
                return None
        except Exception as e:
            logger.error(f"Error fetching vector store ID: {str(e)}")
            return None

    def get_assistant_instructions(self):
        """Get the current instructions for the assistant."""
        logger.info("Fetching assistant instructions.")
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                return None
            instructions = self.openai_service.get_assistant_instructions()
            if instructions:
                logger.info("Assistant instructions retrieved successfully.")
            else:
                logger.warning("Failed to retrieve assistant instructions.")
            return instructions
        except Exception as e:
            logger.error(f"Error fetching assistant instructions: {str(e)}")
            return None

    def get_assistant_temperature(self):
        """Get the current temperature setting for the assistant."""
        logger.info("Fetching assistant temperature.")
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                return None
            temperature = self.openai_service.get_assistant_temperature()
            if temperature is not None:
                logger.info("Assistant temperature retrieved successfully.")
            else:
                logger.warning("Failed to retrieve assistant temperature.")
            return temperature
        except Exception as e:
            logger.error(f"Error fetching assistant temperature: {str(e)}")
            return None

    def get_assistant_top_p(self):
        """Get the current top_p setting for the assistant."""
        logger.info("Fetching assistant top_p.")
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                return None
            top_p = self.openai_service.get_assistant_top_p()
            if top_p is not None:
                logger.info("Assistant top_p retrieved successfully.")
            else:
                logger.warning("Failed to retrieve assistant top_p.")
            return top_p
        except Exception as e:
            logger.error(f"Error fetching assistant top_p: {str(e)}")
            return None

    def update_assistant_instructions(self, new_instructions):
        """Update the instructions for the assistant."""
        logger.info("Updating assistant instructions.")
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                return {'success': False, 'message': 'OpenAI service not initialized'}
            result = self.openai_service.update_assistant_instructions(new_instructions)
            if result['success']:
                logger.info("Assistant instructions updated successfully.")
                # Return the assistant object for UI feedback
                return result
            else:
                logger.warning(f"Failed to update assistant instructions: {result['message']}")
                return result
        except Exception as e:
            logger.error(f"Error updating assistant instructions: {str(e)}")
            return {'success': False, 'message': str(e)}

    def update_assistant_temperature(self, new_temperature):
        """Update the temperature setting for the assistant."""
        logger.info("Updating assistant temperature.")
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                return {'success': False, 'message': 'OpenAI service not initialized'}
            result = self.openai_service.update_assistant_temperature(new_temperature)
            if result['success']:
                logger.info("Assistant temperature updated successfully.")
                return result
            else:
                logger.warning(f"Failed to update assistant temperature: {result['message']}")
                return result
        except Exception as e:
            logger.error(f"Error updating assistant temperature: {str(e)}")
            return {'success': False, 'message': str(e)}

    def update_assistant_top_p(self, new_top_p):
        """Update the top_p setting for the assistant."""
        logger.info("Updating assistant top_p.")
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                return {'success': False, 'message': 'OpenAI service not initialized'}
            result = self.openai_service.update_assistant_top_p(new_top_p)
            if result['success']:
                logger.info("Assistant top_p updated successfully.")
                return result
            else:
                logger.warning(f"Failed to update assistant top_p: {result['message']}")
                return result
        except Exception as e:
            logger.error(f"Error updating assistant top_p: {str(e)}")
            return {'success': False, 'message': str(e)}

    def create_chat_thread(self):
        """
        Creates a new chat thread via OpenAIService.
        Returns the thread ID on success, raises an exception on failure.
        """
        logger.info("Creating new chat thread.")
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                raise PermanentError("OpenAI service not initialized")
            thread_id = self.openai_service.create_thread()
            logger.info(f"Chat thread created successfully with ID: {thread_id}")
            return thread_id
        except Exception as e:
            logger.error(f"Failed to create chat thread: {str(e)}", exc_info=True)
            raise

    def send_message_to_thread(self, thread_id, user_message):
        """
        Sends a message to the specified thread via OpenAIService.
        Returns the assistant's response text.
        """
        logger.info(f"Sending message to thread {thread_id}.")
        try:
            if not self.openai_service:
                logger.error("OpenAI service not initialized")
                raise PermanentError("OpenAI service not initialized")
            response = self.openai_service.send_message_to_thread(thread_id, user_message)
            logger.info(f"Message sent to thread {thread_id} successfully.")
            return response
        except Exception as e:
            logger.error(f"Failed to send message to thread {thread_id}: {str(e)}", exc_info=True)
            raise

    def process_uploaded_image(self, image_bytes):
            """
            Processes image bytes using PIL, calls img_search.process_image, and returns the result.
            """
            logger.info(f"Processing uploaded image ({len(image_bytes)} bytes).")
            if not image_bytes:
                logger.warning("Received empty image bytes.")
                return "Error: No image data received."
            try:
                # Use io.BytesIO to treat bytes as a file
                image_stream = io.BytesIO(image_bytes)
                # Open the image using PIL
                pil_image = Image.open(image_stream)

                # Call the existing process_image function (already imported in backend.py)
                analysis_result = process_image(pil_image, self.client_username)
                logger.info(f"Image processing result: {analysis_result}")
                return analysis_result

            except Image.UnidentifiedImageError:
                logger.error("Could not identify image file. It might be corrupted or not an image.")
                return "Error: Could not read image file. Please upload a valid image."
            except Exception as e:
                logger.error(f"Error processing uploaded image in backend: {str(e)}", exc_info=True)
                # Return a generic error message to the UI
                return f"Error: An unexpected error occurred while processing the image."

    # ------------------------------------------------------------------
    # User Analytics and Statistics
    # ------------------------------------------------------------------
    def get_message_statistics_by_role(self, time_frame="daily", days_back=7):
        """Get message statistics grouped by role and time frame for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching message statistics by role for {time_frame} timeframe, {days_back} days back for client: {self.client_username or 'admin'}")
        try:
            # Note: User model methods need to be updated to support client filtering
            statistics = User.get_message_statistics_by_role(time_frame, days_back, client_username=self.client_username)
            logger.info(f"Successfully fetched message statistics: {len(statistics)} time periods for client: {self.client_username or 'admin'}")
            return statistics
        except Exception as e:
            logger.error(f"Error fetching message statistics for client {self.client_username or 'admin'}: {str(e)}")
            return {}

    def get_user_status_counts(self):
        """Get count of users by status for the current client (optionally filtered by client_username)"""
        self._validate_client_access()
        logger.info(f"Fetching user status counts for client: {self.client_username or 'admin'}")
        try:
            status_counts = User.get_user_status_counts(client_username=self.client_username)
            logger.info(f"Successfully fetched user status counts: {len(status_counts)} statuses for client: {self.client_username or 'admin'}")
            return status_counts
        except Exception as e:
            logger.error(f"Error fetching user status counts for client {self.client_username or 'admin'}: {str(e)}")
            return {}

    def get_user_status_counts_within_timeframe(self, start_date, end_date):
        """Get count of users by status within a specific timeframe for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching user status counts within timeframe: {start_date} to {end_date} for client: {self.client_username or 'admin'}")
        try:
            status_counts = User.get_user_status_counts_within_timeframe(start_date, end_date, client_username=self.client_username)
            logger.info(f"Successfully fetched user status counts within timeframe: {len(status_counts)} statuses for client: {self.client_username or 'admin'}")
            return status_counts
        except Exception as e:
            logger.error(f"Error fetching user status counts within timeframe for client {self.client_username or 'admin'}: {str(e)}")
            return {}

    def get_total_users_count(self):
        """Get total number of users for the current client (optionally filtered by client_username)"""
        self._validate_client_access()
        logger.info(f"Fetching total users count for client: {self.client_username or 'admin'}")
        try:
            total_count = User.get_total_users_count(client_username=self.client_username)
            logger.info(f"Successfully fetched total users count: {total_count} for client: {self.client_username or 'admin'}")
            return total_count
        except Exception as e:
            logger.error(f"Error fetching total users count for client {self.client_username or 'admin'}: {str(e)}")
            return 0

    def get_total_users_count_within_timeframe(self, start_date, end_date):
        """Get total number of users within a specific timeframe for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching total users count within timeframe: {start_date} to {end_date} for client: {self.client_username or 'admin'}")
        try:
            total_count = User.get_total_users_count_within_timeframe(start_date, end_date, client_username=self.client_username)
            logger.info(f"Successfully fetched total users count within timeframe: {total_count} for client: {self.client_username or 'admin'}")
            return total_count
        except Exception as e:
            logger.error(f"Error fetching total users count within timeframe for client {self.client_username or 'admin'}: {str(e)}")
            return 0

    def get_message_statistics_by_role_within_timeframe(self, time_frame, start_date, end_date):
        """Get message statistics grouped by role and time frame within a specific date range for the current client"""
        self._validate_client_access()
        logger.info(f"Fetching message statistics by role for {time_frame} timeframe from {start_date} to {end_date} for client: {self.client_username or 'admin'}")
        try:
            statistics = User.get_message_statistics_by_role_within_timeframe(time_frame, start_date, end_date, client_username=self.client_username)
            logger.info(f"Successfully fetched message statistics within timeframe: {len(statistics)} time periods for client: {self.client_username or 'admin'}")
            return statistics
        except Exception as e:
            logger.error(f"Error fetching message statistics within timeframe for client {self.client_username or 'admin'}: {str(e)}")
            return {}

