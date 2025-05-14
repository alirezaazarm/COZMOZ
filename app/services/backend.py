import logging
from datetime import datetime, timezone
from ..models.appsettings import AppSettings
from ..models.product import Product
from ..models.post import Post
from ..config import Config
import requests
from .instagram_service import InstagramService
from .scraper import CozmozScraper
from .openai_service import OpenAIService
from .img_search import process_image
from PIL import Image
import io
from ..models.additional_info import Additionalinfo
from ..models.admin_user import AdminUser
from ..models.story import Story

logger = logging.getLogger(__name__)

class Backend:
    def __init__(self):
        self.fixed_responses_url = Config.BASE_URL + "/update/fixed-responses"
        self.app_setting_url = Config.BASE_URL + "/update/app-settings"
        self.headers = {"Content-Type": "application/json",  "Authorization": f"Bearer {Config.VERIFY_TOKEN}" }
        self.scraper = CozmozScraper()
        self.openai_service = OpenAIService()
        logger.info("Backend initialized with configuration URLs and headers.")

    # ------------------------------------------------------------------
    # Admin Authentication Methods
    # ------------------------------------------------------------------
    
    def authenticate_admin(self, username, password):
        """Authenticate an admin user by username and password"""
        logger.info(f"Authenticating admin user: {username}")
        try:
            user = AdminUser.authenticate(username, password)
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
            user = AdminUser.get_by_username(username)
            if not user:
                logger.warning(f"Token contains invalid username: {username}")
                return None
                
            if not user.get('is_active', False):
                logger.warning(f"Token contains inactive user: {username}")
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
            users = AdminUser.get_all()
            
            # Format user data for display
            user_data = []
            for user in users:
                username = user.get('username', 'Unknown')
                is_active = user.get('is_active', False)
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
            result = AdminUser.create(username, password, is_active)
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
            user = AdminUser.authenticate(username, current_password)
            if not user:
                logger.warning(f"Password update failed: Current password is incorrect for user '{username}'")
                return False
            
            # Update password
            result = AdminUser.update_password(username, new_password)
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
            result = AdminUser.update_status(username, is_active)
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
            result = AdminUser.delete(username)
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
            result = AdminUser.ensure_default_admin()
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
    # Appsetting to main app
    # ------------------------------------------------------------------
    def app_settings_to_main(self):
        logger.info("Sending app settings to the main server.")
        try:
            # Use the MongoDB AppSettings model directly
            settings = AppSettings.get_all()

            # Make sure settings is not empty
            if not settings:
                logger.warning("No app settings found in database")
                return False

            # Format settings as a list of dictionaries with key-value pairs
            setting_list = []
            for s in settings:
                setting_list.append({s['key']: s['value']})
                if s['key'] == 'vs_id':
                    self.openai_service.set_vs_id({s['key']: s['value']})

            # Log the data being sent for debugging
            logger.info(f"Sending the following app settings: {setting_list}")

            # Send to main app
            response = requests.post(self.app_setting_url, headers=self.headers, json=setting_list)

            # Check response status
            if response.status_code == 200:
                logger.info("App settings successfully sent to the main server.")
                return True
            else:
                logger.error(f"Failed to send app settings. Status code: {response.status_code}")
                logger.error(f"Response text: {response.text}")
                logger.debug(f"Settings data: {setting_list}")
                return False
        except Exception as e:
            logger.error(f"Error in app_settings_to_main: {str(e)}")
            return {"error in app_settings_to_main calling": str(e)}
    
    def get_app_setting(self, key):
        logger.info(f"Fetching app setting for key: {key}.")
        self.app_settings_to_main()
        try:
            # Use the MongoDB AppSettings model directly
            setting = AppSettings.get_by_key(key)
            logger.info(f"App setting for key '{key}' fetched successfully.")
            return setting['value'] if setting else None
        except Exception as e:
            logger.error(f"Error in get_app_setting for key '{key}': {str(e)}")
            return {"error in get_app_setting calling": str(e)}
        
    def update_is_active(self, key, value):
        logger.info(f"Updating app setting for key: {key} with value: {value}.")
        try:
            # Use the MongoDB AppSettings model directly
            result = AppSettings.create_or_update(key, value)
            if result:
                logger.info(f"App setting updated for key: {key}.")
            else:
                logger.error(f"Failed to update app setting for key: {key}.")
            self.app_settings_to_main()
        except Exception as e:
            logger.error(f"Error in update_is_active for key '{key}': {str(e)}")
            return {"error in update_is_active": str(e)}

    # ------------------------------------------------------------------
    # Data : Product + additional info
    # ------------------------------------------------------------------

    def update_products(self):
        logger.info("Scraping the site is starting...")
        try:
            self.scraper.update_products()
            logger.info("Update products completed.")
        except Exception as e:
            logger.error(f"Failed to update products: {str(e)}", exc_info=True)
            return False

        try:
            self.app_settings_to_main()
        except Exception as e:
            logger.error(f"Failed to send app settings: {e}")
            
        return True

    def get_products(self):
        logger.info("Fetching products from the database.")
        try:
            # Use the MongoDB Product model directly
            products = Product.get_all()
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
            logger.info(f"Successfully fetched {len(products_data)} products.")
            return products_data
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return []

    def get_additionalinfo(self):
        """Return all additional text entries as a list of dicts with 'key' and 'value'."""
        try:
            entries = Additionalinfo.get_all()
            return [
                {"key": entry["title"], "value": entry["content"]}
                for entry in entries
            ]
        except Exception as e:
            logger.error(f"Error fetching all additional text entries: {str(e)}")
            return []

    def add_additionalinfo(self, key, value):
        """Add or update a text entry in the additional_text collection with the given key and value."""
        logger.info(f"Adding/updating additional text: {key}")
        try:
            # Check if an entry with this title already exists
            existing = Additionalinfo.search(key)
            if existing and len(existing) > 0:
                # Update existing entry
                result = Additionalinfo.update(str(existing[0]['_id']), {
                    "title": key,
                    "content": value
                })
            else:
                # Create new entry
                result = Additionalinfo.create(title=key, content=value)

            if result:
                logger.info(f"Additional text '{key}' created/updated successfully.")
                return True
            else:
                logger.error(f"Failed to create/update additional text '{key}'.")
                return False
        except Exception as e:
            logger.error(f"Error creating/updating additional text '{key}': {str(e)}")
            return False

    def delete_additionalinfo(self, key):
        """Delete an additional text entry by title."""
        try:
            # Find the entry with the matching title
            entries = Additionalinfo.search(key)
            if not entries or len(entries) == 0:
                logger.error(f"Additional text entry with title '{key}' not found.")
                return False

            # delete file from openai if it has file_id
            if entries[0]['file_id']:
                resp = self.openai_service.delete_single_file(entries[0]['file_id'])     
                if resp:
                    result = Additionalinfo.delete(str(entries[0]['_id']))
                    if result:
                        logger.info(f"Additional text title '{key}' deleted from DB successfully.")
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
                    logger.info(f"Additional text title '{key}' deleted from DB successfully.")
                    return True
                else:
                    logger.error(f"Failed to delete additional text title '{key}' from DB.")
                    return False

        except Exception as e:
            logger.error(f"Error deleting additional text entry '{key}': {str(e)}")
            return False
        
    def rebuild_files_and_vs(self):
        try:
            clear_success = self.openai_service.rebuild_all()
            if clear_success:
                logger.info("Additional info files and vector store rebuilt successfully")
                return True
            else:
                logger.error("Failed to rebuild additional info files and vector store")
                return False
        except Exception as e:
            logger.error(f"Error in update_additionalinfo_files_and_vs: {str(e)}")
            return False
            
    # ------------------------------------------------------------------
    # Instagram management : Posts + Stories
    # ------------------------------------------------------------------
    #                     ---- vision ----

    def set_label(self, post_id, label):
        """
        Sets the label for a specific Instagram post identified by its Post ID.
        Returns True if the post was found and the update was attempted, False otherwise.
        """
        logger.info(f"Setting label '{label}' for post ID: {post_id}.")
        if not post_id:
            logger.error("Cannot set label: post_id is missing or invalid.")
            return False
        try:
            # Ensure label is a string, trim whitespace
            label_to_set = str(label).strip() if label is not None else ""

            success = Post.update(post_id, {"label": label_to_set})

            if success:
                logger.info(f"Label update attempted for post ID: {post_id}. Label set to '{label_to_set}'.")
                return True
            else:
                logger.warning(f"Could not set label for post ID {post_id}. Post not found.")
                return False
        except Exception as e:
            logger.error(f"Error setting label for post ID {post_id}: {str(e)}", exc_info=True)
            return False

    def set_labels_by_model(self):
        """
        Identifies unlabeled posts, downloads their images, uses img_search.process_image
        to predict a label (product title), and updates the post's label if a prediction is found.
        """
        logger.info("Starting automatic labeling of posts by model.")
        processed_count = 0
        labeled_count = 0
        errors = []

        try:
            # 1. Get all posts from the database
            all_posts = Post.get_all()
            if not all_posts:
                logger.info("No posts found in the database.")
                return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'No posts found.'}

            # 2. Filter for posts that are unlabeled (label is missing, None, or empty string)
            unlabeled_posts = [
                post for post in all_posts
                if not post.get('label')
            ]
            logger.info(f"Found {len(unlabeled_posts)} posts without labels.")

            if not unlabeled_posts:
                 return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'All posts are already labeled.'}

            # 3. Iterate through unlabeled posts
            for post in unlabeled_posts:
                post_id = post.get('id') # Instagram's post ID
                thumbnail_url = post.get('thumbnail_url')
                media_url = post.get('media_url')
                processed_count += 1

                if not post_id:
                    logger.warning(f"Skipping post due to missing 'id': MongoDB _id {post.get('_id', 'N/A')}")
                    errors.append(f"Post missing Instagram ID: MongoDB _id {post.get('_id', 'N/A')}")
                    continue

                if not media_url:
                    logger.warning(f"Skipping post ID {post_id} due to missing 'media_url'.")
                    errors.append(f"Post ID {post_id} missing media_url.")
                    continue

                try:
                    # 4. Download the image content
                    logger.debug(f"Downloading image for post ID {post_id} from {media_url}")

                    if thumbnail_url:
                        response = requests.get(thumbnail_url, stream=True, timeout=20) # Increased timeout
                        response.raise_for_status()
                    else:
                        response = requests.get(media_url, stream=True, timeout=20) # Increased timeout
                        response.raise_for_status() # Check for HTTP errors

                    image_bytes = response.content
                    if not image_bytes:
                        logger.warning(f"Downloaded image for post ID {post_id} is empty.")
                        errors.append(f"Empty image downloaded for post ID {post_id}.")
                        continue

                    # 5. Process the image using the imported function
                    logger.debug(f"Processing image for post ID {post_id}")
                    # Assuming process_image takes image bytes and returns the top label string or None

                    image_stream = io.BytesIO(image_bytes)
                    pil_image = Image.open(image_stream)
                    predicted_label = process_image(pil_image)

                    # 6. If a label was predicted, update the post
                    if predicted_label:
                        logger.info(f"Post ID {post_id}: Model predicted label '{predicted_label}'. Setting label.")
                        # Use the existing set_label method which handles DB update
                        label_set_success = self.set_label(post_id, predicted_label)
                        if label_set_success:
                            labeled_count += 1
                        else:
                             # set_label logs warnings/errors internally
                             errors.append(f"Failed to set label for post ID {post_id} after prediction '{predicted_label}'.")
                    else:
                        logger.info(f"Post ID {post_id}: Model did not return a confident label.")

                except requests.exceptions.RequestException as e:
                    logger.error(f"Failed to download image for post ID {post_id} from {media_url}: {e}")
                    errors.append(f"Download failed for post ID {post_id}: {e}")
                except Exception as e:
                    # Catch errors from process_image or set_label
                    logger.error(f"Error processing image or setting label for post ID {post_id}: {e}", exc_info=True)
                    errors.append(f"Processing/SetLabel error for post ID {post_id}: {e}")

            # 7. Construct and return the result summary
            message = f"Processed {processed_count} unlabeled posts. Set labels for {labeled_count} posts."
            success_status = not errors # Success is true only if there are no errors

            if errors:
                # Log first few errors for brevity in the message
                error_summary = '; '.join(errors[:3]) + ('...' if len(errors) > 3 else '')
                message += f" Encountered {len(errors)} errors. First few: {error_summary}"
                logger.warning(f"Automatic labeling completed with {len(errors)} errors. Full list: {errors}")
                return {'success': success_status, 'processed': processed_count, 'labeled': labeled_count, 'message': message, 'errors': errors}
            else:
                logger.info("Automatic labeling completed successfully.")
                return {'success': success_status, 'processed': processed_count, 'labeled': labeled_count, 'message': message}

        except Exception as e:
            # Catch unexpected errors during the overall process (e.g., DB connection)
            logger.error(f"An unexpected error occurred during set_labels_by_model: {e}", exc_info=True)
            return {'success': False, 'processed': processed_count, 'labeled': labeled_count, 'message': f"An unexpected error occurred: {e}"}

    def download_posts_label(self):
        """
        Creates a JSON object with post labels as keys and lists of image URLs as values.
        For each label, the value is a list of thumbnail_urls (or media_urls if thumbnail is None).
        Returns a dictionary in the format: {"label1": ["url1", "url2"], "label2": ["url3", "url4"], ...}
        """
        logger.info("Preparing posts organized by labels")
        try:
            # Get all posts
            posts = Post.get_all()
            
            if not posts:
                logger.info("No posts found in database")
                return {}
                
            # Initialize the result dictionary
            labeled_posts = {}
            
            # Process each post
            for post in posts:
                # Get the label (or use "Unlabeled" if none exists)
                label = post.get('label', '')
                if not label:
                    continue
                    
                # Get the image URL (preferring thumbnail if it exists)
                image_url = post.get('thumbnail_url') or post.get('media_url')
                
                # Skip if no image URL
                if not image_url:
                    continue
                    
                # Add to the appropriate label list
                if label not in labeled_posts:
                    labeled_posts[label] = []
                    
                labeled_posts[label].append(image_url)
            
            logger.info(f"Successfully prepared posts by label, found {len(labeled_posts)} unique labels")
            
            # Log some stats about the data
            for label, urls in labeled_posts.items():
                logger.debug(f"Label '{label}' has {len(urls)} images")
                
            return labeled_posts
            
        except Exception as e:
            logger.error(f"Error preparing posts by label: {str(e)}", exc_info=True)
            return {"error": str(e)}

    #                      ---- Post ----

    def fetch_instagram_posts(self):
        """
        Fetch Instagram posts via InstagramService and store them in the DB.
        Returns True if successful, False otherwise.
        """
        logger.info("Fetching Instagram posts.")
        try:
            result = InstagramService.get_posts()
            if result:
                logger.info("Instagram posts fetched successfully.")
            else:
                logger.warning("Failed to fetch Instagram posts.")
            return result
        except Exception as e:
            logger.error(f"Failed to fetch Instagram posts: {str(e)}", exc_info=True)
            return False

    def get_posts(self):
        """
        Retrieves stored Instagram posts, returning their media_url and caption.
        """
        logger.info("Fetching stored Instagram posts.")
        try:
            # Use the MongoDB InstagramPost model directly
            posts = Post.get_all()

            # Extract required fields
            post_data = [
                {
                    "id": post.get('id'),  # Include the Instagram ID for labeling
                    "media_url": post.get('media_url'),
                    "thumbnail_url": post.get('thumbnail_url'),
                    "caption": post.get('caption'),
                    "label": post.get('label', ''),
                }
                for post in posts if post.get('media_url')  # Ensure media_url exists
            ]

            logger.info(f"Successfully fetched {len(post_data)} Instagram posts.")
            return post_data
        except Exception as e:
            logger.error(f"Error fetching stored Instagram posts: {str(e)}", exc_info=True)
            return []  # Return empty list on error

    def get_posts_fixed_response(self, post_id):
        """
        Get fixed response for a post by its ID.
        Returns the fixed response object if found, None otherwise.
        """
        logger.info(f"Fetching fixed response for post ID: {post_id}")
        try:
            post = Post.get_by_instagram_id(post_id)
            if post and post.get('fixed_response'):
                logger.info(f"Fixed response found for post ID: {post_id}")
                return post['fixed_response']
            else:
                logger.info(f"No fixed response found for post ID: {post_id}")
                return None
        except Exception as e:
            logger.error(f"Error fetching fixed response for post ID {post_id}: {str(e)}")
            return None
    
    def create_or_update_post_fixed_response(self, post_id, trigger_keyword, comment_response_text=None, direct_response_text=None):
        """
        Create or update a fixed response for a post.
        Returns True if successful, False otherwise.
        """
        logger.info(f"Creating/updating fixed response for post ID: {post_id}")
        try:
            result = Post.set_fixed_response(
                post_id=post_id,
                trigger_keyword=trigger_keyword,
                comment_response_text=comment_response_text,
                direct_response_text=direct_response_text
            )
            if result:
                logger.info(f"Fixed response created/updated successfully for post ID: {post_id}")
                return True
            else:
                logger.warning(f"Failed to create/update fixed response for post ID: {post_id}")
                return False
        except Exception as e:
            logger.error(f"Error creating/updating fixed response for post ID {post_id}: {str(e)}")
            return False
    
    def delete_post_fixed_response(self, post_id):
        """
        Delete a fixed response for a post by its ID.
        Returns True if successful, False otherwise.
        """
        logger.info(f"Deleting fixed response for post ID: {post_id}")
        try:
            result = Post.remove_fixed_response(post_id)
            if result:
                logger.info(f"Fixed response deleted successfully for post ID: {post_id}")
                return True
            else:
                logger.warning(f"Failed to delete fixed response for post ID: {post_id}")
                return False
        except Exception as e:
            logger.error(f"Error deleting fixed response for post ID {post_id}: {str(e)}")
            return False

    def get_post_metadata(self, post_id):
        """
        Get metadata for a specific post.
        Returns a dictionary with media_type, like_count, and timestamp.
        """
        logger.info(f"Fetching metadata for post ID: {post_id}")
        try:
            # Use the specialized method to get post by Instagram ID
            post = Post.get_by_instagram_id(post_id)
            
            if post:
                metadata = {
                    "media_type": post.get('media_type', 'Unknown'),
                    "like_count": post.get('like_count', 0),
                    "timestamp": post.get('timestamp', 'Unknown date')
                }
                logger.info(f"Metadata retrieved for post ID: {post_id}")
                return metadata
            else:
                logger.warning(f"Post with ID {post_id} not found for metadata retrieval")
                return {
                    "media_type": 'Unknown',
                    "like_count": 0,
                    "timestamp": 'Unknown date'
                }
        except Exception as e:
            logger.error(f"Error retrieving metadata for post ID {post_id}: {str(e)}")
            return {
                "media_type": 'Error',
                "like_count": 0,
                "timestamp": 'Error retrieving data'
            }

    #                       ---- Story ----
   
    def fetch_instagram_stories(self):
        """
        Fetch Instagram stories via InstagramService and store them in the DB.
        Returns True if successful, False otherwise.
        """
        logger.info("Fetching Instagram stories.")
        try:
            result = InstagramService.get_stories()
            if result:
                logger.info("Instagram stories fetched successfully.")
            else:
                logger.warning("Failed to fetch Instagram stories.")
            return result
        except Exception as e:
            logger.error(f"Failed to fetch Instagram stories: {str(e)}", exc_info=True)
            return False

    def get_stories(self):
        """
        Retrieves stored Instagram stories, returning their media_url and caption.
        """
        logger.info("Fetching stored Instagram stories.")
        try:
            # Use the MongoDB Story model directly
            stories = Story.get_all()

            # Extract required fields
            story_data = [
                {
                    "id": story.get('id'),  # Include the Instagram ID for labeling
                    "media_url": story.get('media_url'),
                    "thumbnail_url": story.get('thumbnail_url'),
                    "caption": story.get('caption'),
                }
                for story in stories if story.get('media_url')  # Ensure media_url exists
            ]

            logger.info(f"Successfully fetched {len(story_data)} Instagram stories.")
            return story_data
        except Exception as e:
            logger.error(f"Error fetching stored Instagram stories: {str(e)}", exc_info=True)
            return []  # Return empty list on error

    def get_story_fixed_response(self, story_id):
        """
        Get fixed response for a story by its ID.
        Returns the fixed response object if found, None otherwise.
        """
        logger.info(f"Fetching fixed response for story ID: {story_id}")
        try:
            # Use the Story model's method to get fixed response by story ID
            fixed_response = Story.get_fixed_response_by_story(story_id)
            if fixed_response:
                logger.info(f"Fixed response found for story ID: {story_id}")
                return fixed_response
            else:
                logger.info(f"No fixed response found for story ID: {story_id}")
                return None
        except Exception as e:
            logger.error(f"Error fetching fixed response for story ID {story_id}: {str(e)}")
            return None
    
    def create_or_update_story_fixed_response(self, story_id, trigger_keyword, direct_response_text=None):
        """
        Create or update a fixed response for a story.
        Returns True if successful, False otherwise.
        """
        logger.info(f"Creating/updating fixed response for story ID: {story_id}")
        try:
            result = Story.create_or_update_fixed_response(
                story_id=story_id,
                trigger_keyword=trigger_keyword,
                direct_response_text=direct_response_text
            )
            if result:
                logger.info(f"Fixed response created/updated successfully for story ID: {story_id}")
                return True
            else:
                logger.warning(f"Failed to create/update fixed response for story ID: {story_id}")
                return False
        except Exception as e:
            logger.error(f"Error creating/updating fixed response for story ID {story_id}: {str(e)}")
            return False
    
    def delete_story_fixed_response(self, story_id):
        """
        Delete a fixed response for a story by its ID.
        Returns True if successful, False otherwise.
        """
        logger.info(f"Deleting fixed response for story ID: {story_id}")
        try:
            result = Story.delete_fixed_response_by_story(story_id)
            if result:
                logger.info(f"Fixed response deleted successfully for story ID: {story_id}")
                return True
            else:
                logger.warning(f"Failed to delete fixed response for story ID: {story_id}")
                return False
        except Exception as e:
            logger.error(f"Error deleting fixed response for story ID {story_id}: {str(e)}")
            return False

    def get_story_metadata(self, story_id):
        """
        Get metadata for a specific story.
        Returns a dictionary with media_type, like_count, and timestamp.
        """
        logger.info(f"Fetching metadata for story ID: {story_id}")
        try:
            stories = Story.get_all()
            story = next((s for s in stories if s.get('id') == story_id), None)
            
            if story:
                metadata = {
                    "media_type": story.get('media_type', 'Unknown'),
                    "like_count": story.get('like_count', 0),
                    "timestamp": story.get('timestamp', 'Unknown date')
                }
                logger.info(f"Metadata retrieved for story ID: {story_id}")
                return metadata
            else:
                logger.warning(f"Story with ID {story_id} not found for metadata retrieval")
                return {
                    "media_type": 'Unknown',
                    "like_count": 0,
                    "timestamp": 'Unknown date'
                }
        except Exception as e:
            logger.error(f"Error retrieving metadata for story ID {story_id}: {str(e)}")
            return {
                "media_type": 'Error',
                "like_count": 0,
                "timestamp": 'Error retrieving data'
            }

    # ------------------------------------------------------------------
    # Openai management
    # ------------------------------------------------------------------

    def get_vs_id(self):
        """Get the store IDs from the database."""
        logger.info("Fetching current vector store ID.")
        try:
            # Use the MongoDB AppSettings model directly
            vs_id = AppSettings.get_by_key('vs_id')
            if vs_id:
                logger.info(f"Current vector store ID: {vs_id['value']}")
                return [vs_id['value']]
            else:
                logger.info("No vector store ID found in database.")
                return None
        except Exception as e:
            logger.error(f"Error fetching vector store ID: {str(e)}")
            return None

    def get_assistant_instructions(self):
        """Get the current instructions for the assistant."""
        logger.info("Fetching assistant instructions.")
        try:
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
                analysis_result = process_image(pil_image)
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
    # Fixed response methods for post detail view
    # ------------------------------------------------------------------
    

    def set_single_label(self, post_id):
        """
        Processes a single post image using the vision model and sets its label.
        Returns the predicted label if successful, or an error message.
        """
        logger.info(f"Processing post ID {post_id} for automatic labeling.")
        try:
            # Get the post by its ID
            post = Post.get_by_instagram_id(post_id)
            if not post:
                logger.warning(f"Post with ID {post_id} not found.")
                return {"success": False, "message": "Post not found"}
            
            # Check if media URL exists
            media_url = post.get('media_url')
            thumbnail_url = post.get('thumbnail_url')
            
            if not media_url and not thumbnail_url:
                logger.warning(f"Post ID {post_id} has no media URL or thumbnail URL.")
                return {"success": False, "message": "No image URL available"}
            
            # Try to download the image (prefer thumbnail if available)
            try:
                url_to_use = thumbnail_url if thumbnail_url else media_url
                logger.info(f"Downloading image for post ID {post_id} from {url_to_use}")
                
                response = requests.get(url_to_use, stream=True, timeout=20)
                response.raise_for_status()
                
                image_bytes = response.content
                if not image_bytes:
                    return {"success": False, "message": "Downloaded image is empty"}
                
                # Process the image
                image_stream = io.BytesIO(image_bytes)
                pil_image = Image.open(image_stream)
                predicted_label = process_image(pil_image)
                
                if not predicted_label or predicted_label == "Not certain":
                    logger.info(f"Model couldn't find a confident label for post ID {post_id}")
                    return {"success": False, "message": "Model couldn't determine a label with confidence"}
                
                # Extract just the label part after the confidence score (format is "0.8==>Label")
                if "==>" in predicted_label:
                    confidence, label = predicted_label.split("==>")
                    predicted_label = label
                
                # Set the label
                label_set_success = self.set_label(post_id, predicted_label)
                
                if label_set_success:
                    logger.info(f"Post ID {post_id} automatically labeled as '{predicted_label}'")
                    return {"success": True, "label": predicted_label}
                else:
                    return {"success": False, "message": "Failed to set label in database"}
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download image: {str(e)}")
                return {"success": False, "message": f"Failed to download image: {str(e)}"}
            
        except Exception as e:
            logger.error(f"Error in set_single_label for post ID {post_id}: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Error: {str(e)}"}




