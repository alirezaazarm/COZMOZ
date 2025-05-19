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
from app.utils.helpers import  expand_triggers

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
    # Appsetting  ---> main app
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
            self.send_all_fixed_responses_to_main()
        except Exception as e:
            logger.error(f"Error in update_is_active for key '{key}': {str(e)}")
            return {"error in update_is_active": str(e)}
    # ------------------------------------------------------------------
    # Fixed responses ---> main app
    # ------------------------------------------------------------------
    def send_comment_fixed_responses_to_main(self, comment_fixed_responses):
        """
        Send the comment fixed responses dict to the main app to update in-memory cache.
        The dict should be structured as:
        {
            "POST_ID_1": expand_triggers({
                "trigger1": {"comment": "Reply text", "DM": "Direct message text"},
                ...
            }),
            ...
        }
        Use expand_triggers to ensure all numeral variants are included for each trigger.
        """
        # Expand triggers for each post before sending
        expanded_dict = {post_id: expand_triggers(triggers) for post_id, triggers in comment_fixed_responses.items()}
        url = Config.BASE_URL + "/update/fixed-responses/comments"
        logger.info(f"Sending comment fixed responses to {url}")
        try:
            response = requests.post(url, headers=self.headers, json=expanded_dict)
            if response.status_code == 200:
                logger.info("Comment fixed responses successfully sent to main app.")
                return True
            else:
                logger.error(f"Failed to send comment fixed responses. Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending comment fixed responses: {str(e)}")
            return False

    def send_story_fixed_responses_to_main(self, story_fixed_responses):
        """
        Send the story fixed responses dict to the main app to update in-memory cache.
        The dict should be structured as:
        {
            "STORY_ID_1": {"trigger_keyword": "trigger", "direct_response_text": "DM text"},
            ...
        }
        The trigger_keyword for each story will be expanded to include all numeral variants using expand_triggers.
        """
        # Expand trigger_keyword for each story before sending
        expanded_dict = {}
        for story_id, response in story_fixed_responses.items():
            trigger = response.get('trigger_keyword')
            if trigger:
                # Expand the trigger to all numeral variants
                for variant in expand_triggers({trigger: None}).keys():
                    expanded_dict[story_id + '__' + variant] = {
                        **response,
                        'trigger_keyword': variant
                    }
            else:
                expanded_dict[story_id] = response
        url = Config.BASE_URL + "/update/fixed-responses/stories"
        logger.info(f"Sending story fixed responses to {url}")
        try:
            response = requests.post(url, headers=self.headers, json=expanded_dict)
            if response.status_code == 200:
                logger.info("Story fixed responses successfully sent to main app.")
                return True
            else:
                logger.error(f"Failed to send story fixed responses. Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending story fixed responses: {str(e)}")
            return False

    def send_all_fixed_responses_to_main(self):
        """
        Fetch all fixed responses from posts and stories and send them to the main app.
        Returns a dict summarizing the result.
        """
        logger.info("Fetching all fixed responses from posts and stories.")
        post_fixed = Post.get_all_fixed_responses_structured()
        story_fixed = Story.get_all_fixed_responses_structured()
        logger.info(f"Found {len(post_fixed)} post fixed responses and {len(story_fixed)} story fixed responses.")
        post_result = self.send_comment_fixed_responses_to_main(post_fixed)
        story_result = self.send_story_fixed_responses_to_main(story_fixed)
        logger.info(f"Post fixed responses sent: {post_result}, Story fixed responses sent: {story_result}")
        return {"post_fixed_sent": post_result, "story_fixed_sent": story_result}
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
            predicted_label = process_image(pil_image) # Assumes process_image returns label or None

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
        logger.info("Fetching Instagram posts.")
        try:
            result = InstagramService.get_posts()
            if result: logger.info("Instagram posts fetched/updated successfully.")
            else: logger.warning("Failed to fetch/update Instagram posts.")
            return result
        except Exception as e: logger.error(f"Failed to fetch Instagram posts: {str(e)}", exc_info=True); return False

    def get_posts(self):
        logger.info("Fetching stored Instagram posts.")
        try:
            posts = Post.get_all()
            post_data = [
                {"id": post.get('id'), "media_url": post.get('media_url'), "thumbnail_url": post.get('thumbnail_url'),
                 "caption": post.get('caption'), "label": post.get('label', ''), "media_type": post.get('media_type')}
                for post in posts if post.get('id') # Ensure id exists
            ]
            logger.info(f"Successfully fetched {len(post_data)} Instagram posts.")
            return post_data
        except Exception as e: logger.error(f"Error fetching stored Instagram posts: {str(e)}", exc_info=True); return []

    def set_post_label(self, post_id, label):
        logger.info(f"Setting label '{label}' for post ID: {post_id}.")
        if not post_id: logger.error("Cannot set post label: post_id is missing."); return False
        try:
            success = Post.set_label(post_id, label)
            if success: logger.info(f"Label update successful for post ID: {post_id}."); return True
            else: logger.warning(f"Could not set label for post ID {post_id}."); return False
        except Exception as e: logger.error(f"Error setting label for post ID {post_id}: {str(e)}", exc_info=True); return False

    def remove_post_label(self, post_id):
        logger.info(f"Removing label for post ID: {post_id}.")
        if not post_id: logger.error("Cannot remove post label: post_id is missing."); return False
        try:
            success = Post.remove_label(post_id) # This sets label to ""
            if success: logger.info(f"Label removed for post ID: {post_id}."); return True
            else: logger.warning(f"Could not remove label for post ID {post_id}."); return False
        except Exception as e: logger.error(f"Error removing label for post ID {post_id}: {str(e)}", exc_info=True); return False

    def unset_all_post_labels(self):
        logger.info("Unsetting labels from all posts.")
        try:
            updated_count = Post.unset_all_labels()
            logger.info(f"Successfully unset labels from {updated_count} posts.")
            return updated_count
        except Exception as e: logger.error(f"Error unsetting all post labels: {str(e)}", exc_info=True); return 0

    def set_single_post_label_by_model(self, post_id):
        logger.info(f"Processing post ID {post_id} for automatic labeling.")
        try:
            post = Post.get_by_instagram_id(post_id)
            if not post:
                logger.warning(f"Post with ID {post_id} not found."); return {"success": False, "message": "Post not found"}

            predicted_label, error_msg = self._process_media_for_labeling(post_id, post.get('media_url'), post.get('thumbnail_url'), "post")
            if error_msg:
                return {"success": False, "message": error_msg}

            if predicted_label:
                label_set_success = self.set_post_label(post_id, predicted_label)
                if label_set_success:
                    logger.info(f"Post ID {post_id} automatically labeled as '{predicted_label}'")
                    return {"success": True, "label": predicted_label}
                else:
                    return {"success": False, "message": "Failed to set label in database"}
            return {"success": False, "message": "Model couldn't determine a label"} # Should be caught by _process_media_for_labeling

        except Exception as e:
            logger.error(f"Error in set_single_post_label_by_model for post ID {post_id}: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def set_post_labels_by_model(self):
        logger.info("Starting automatic labeling of posts by model.")
        processed_count, labeled_count, errors = 0, 0, []
        all_posts = Post.get_all()
        if not all_posts:
            return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'No posts found.'}

        unlabeled_posts = [p for p in all_posts if not p.get('label')]
        logger.info(f"Found {len(unlabeled_posts)} posts without labels.")
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

        message = f"Processed {processed_count} unlabeled posts. Set labels for {labeled_count} posts."
        if errors: message += f" Encountered {len(errors)} errors. First few: {'; '.join(errors[:3])}"
        logger.info(message)
        return {'success': not errors, 'processed': processed_count, 'labeled': labeled_count, 'message': message, 'errors': errors}

    def download_post_labels(self):
        logger.info("Preparing posts organized by labels for download.")
        try:
            posts = Post.get_all()
            if not posts: return {}
            labeled_posts = {}
            for post in posts:
                label = post.get('label', '').strip()
                if not label: continue # Skip unlabeled or empty-label posts
                image_url = post.get('thumbnail_url') or post.get('media_url')
                if not image_url: continue
                if label not in labeled_posts: labeled_posts[label] = []
                labeled_posts[label].append(image_url)
            logger.info(f"Successfully prepared posts by label, found {len(labeled_posts)} unique labels.")
            return labeled_posts
        except Exception as e: logger.error(f"Error preparing post labels for download: {str(e)}", exc_info=True); return {"error": str(e)}

    def get_post_fixed_response(self, post_id):
        logger.info(f"Fetching fixed response for post ID: {post_id}")
        try:
            response = Post.get_fixed_response(post_id) # Use the model method
            if response: logger.info(f"Fixed response found for post ID: {post_id}"); return response
            else: logger.info(f"No fixed response found for post ID: {post_id}"); return None
        except Exception as e: logger.error(f"Error fetching fixed response for post ID {post_id}: {str(e)}"); return None

    def create_or_update_post_fixed_response(self, post_id, trigger_keyword, comment_response_text=None, direct_response_text=None):
        logger.info(f"Creating/updating fixed response for post ID: {post_id}")
        try:
            # Use the model method
            result = Post.set_fixed_response(post_id, trigger_keyword, comment_response_text, direct_response_text)
            if result: logger.info(f"Fixed response C/U successful for post ID: {post_id}"); return True
            else: logger.warning(f"Failed to C/U fixed response for post ID: {post_id}"); return False
        except Exception as e: logger.error(f"Error C/U fixed response for post ID {post_id}: {str(e)}"); return False

    def delete_post_fixed_response(self, post_id):
        logger.info(f"Deleting fixed response for post ID: {post_id}")
        try:
            result = Post.delete_fixed_response(post_id) # Use the model method
            if result: logger.info(f"Fixed response deleted successfully for post ID: {post_id}"); return True
            else: logger.warning(f"Failed to delete fixed response for post ID: {post_id}"); return False
        except Exception as e: logger.error(f"Error deleting fixed response for post ID {post_id}: {str(e)}"); return False

    def set_post_admin_explanation(self, post_id, explanation):
        logger.info(f"Setting admin explanation for post ID: {post_id}")
        try:
            result = Post.set_admin_explanation(post_id, explanation) # Use the model method
            if result: logger.info(f"Admin explanation set for post ID: {post_id}"); return True
            else: logger.warning(f"Failed to set admin explanation for post ID: {post_id}"); return False
        except Exception as e: logger.error(f"Error setting admin explanation for post ID {post_id}: {str(e)}"); return False

    def get_post_admin_explanation(self, post_id):
        logger.info(f"Fetching admin explanation for post ID: {post_id}")
        try:
            explanation = Post.get_admin_explanation(post_id) # Use the model method
            if explanation is not None: logger.info(f"Admin explanation found for post ID: {post_id}"); return explanation
            else: logger.info(f"No admin explanation for post ID: {post_id}"); return None # Distinguish empty from not found
        except Exception as e: logger.error(f"Error fetching admin explanation for post ID {post_id}: {str(e)}"); return None

    def remove_post_admin_explanation(self, post_id):
        logger.info(f"Removing admin explanation for post ID: {post_id}")
        try:
            result = Post.remove_admin_explanation(post_id) # Use the model method
            if result: logger.info(f"Admin explanation removed for post ID: {post_id}"); return True
            else: logger.warning(f"Failed to remove admin explanation for post ID: {post_id}"); return False
        except Exception as e: logger.error(f"Error removing admin explanation for post ID {post_id}: {str(e)}"); return False

    # --- Story Methods (Paired with Post Methods) ---
    def fetch_instagram_stories(self):
        logger.info("Fetching Instagram stories.")
        try:
            # InstagramService.get_stories should ideally call Story.create_or_update_from_instagram
            result = InstagramService.get_stories()
            if result: logger.info("Instagram stories fetched/updated successfully.")
            else: logger.warning("Failed to fetch/update Instagram stories.")
            return result
        except Exception as e: logger.error(f"Failed to fetch Instagram stories: {str(e)}", exc_info=True); return False

    def get_stories(self):
        logger.info("Fetching stored Instagram stories.")
        try:
            stories = Story.get_all() # Fetches from DB
            story_data = [
                {"id": story.get('id'), "media_url": story.get('media_url'), "thumbnail_url": story.get('thumbnail_url'),
                 "caption": story.get('caption'), "label": story.get('label', ''), "media_type": story.get('media_type')}
                for story in stories if story.get('id') # Ensure id exists
            ]
            logger.info(f"Successfully fetched {len(story_data)} Instagram stories from DB.")
            return story_data
        except Exception as e: logger.error(f"Error fetching stored Instagram stories: {str(e)}", exc_info=True); return []

    def set_story_label(self, story_id, label):
        logger.info(f"Setting label '{label}' for story ID: {story_id}.")
        if not story_id: logger.error("Cannot set story label: story_id is missing."); return False
        try:
            success = Story.set_label(story_id, label)
            if success: logger.info(f"Label update successful for story ID: {story_id}."); return True
            else: logger.warning(f"Could not set label for story ID {story_id}."); return False
        except Exception as e: logger.error(f"Error setting label for story ID {story_id}: {str(e)}", exc_info=True); return False

    def remove_story_label(self, story_id):
        logger.info(f"Removing label for story ID: {story_id}.")
        if not story_id: logger.error("Cannot remove story label: story_id is missing."); return False
        try:
            success = Story.remove_label(story_id)
            if success: logger.info(f"Label removed for story ID: {story_id}."); return True
            else: logger.warning(f"Could not remove label for story ID {story_id}."); return False
        except Exception as e: logger.error(f"Error removing label for story ID {story_id}: {str(e)}", exc_info=True); return False

    def unset_all_story_labels(self):
        logger.info("Unsetting labels from all stories.")
        try:
            updated_count = Story.unset_all_labels()
            logger.info(f"Successfully unset labels from {updated_count} stories.")
            return updated_count
        except Exception as e: logger.error(f"Error unsetting all story labels: {str(e)}", exc_info=True); return 0

    def set_single_story_label_by_model(self, story_id):
        logger.info(f"Processing story ID {story_id} for automatic labeling.")
        try:
            story = Story.get_by_instagram_id(story_id)
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
        logger.info("Starting automatic labeling of stories by model.")
        processed_count, labeled_count, errors = 0, 0, []
        all_stories = Story.get_all()
        if not all_stories:
            return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'No stories found.'}

        unlabeled_stories = [s for s in all_stories if not s.get('label')]
        logger.info(f"Found {len(unlabeled_stories)} stories without labels.")
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

        message = f"Processed {processed_count} unlabeled stories. Set labels for {labeled_count} stories."
        if errors: message += f" Encountered {len(errors)} errors. First few: {'; '.join(errors[:3])}"
        logger.info(message)
        return {'success': not errors, 'processed': processed_count, 'labeled': labeled_count, 'message': message, 'errors': errors}

    def download_story_labels(self):
        logger.info("Preparing stories organized by labels for download.")
        try:
            stories = Story.get_all()
            if not stories: return {}
            labeled_stories = {}
            for story in stories:
                label = story.get('label', '').strip()
                if not label: continue
                image_url = story.get('thumbnail_url') or story.get('media_url') # Prefer thumbnail
                if not image_url: continue
                if label not in labeled_stories: labeled_stories[label] = []
                labeled_stories[label].append(image_url)
            logger.info(f"Successfully prepared stories by label, found {len(labeled_stories)} unique labels.")
            return labeled_stories
        except Exception as e: logger.error(f"Error preparing story labels for download: {str(e)}", exc_info=True); return {"error": str(e)}

    def get_story_fixed_response(self, story_id):
        logger.info(f"Fetching fixed response for story ID: {story_id}")
        try:
            response = Story.get_fixed_response(story_id) # Use the model method
            if response: logger.info(f"Fixed response found for story ID: {story_id}"); return response
            else: logger.info(f"No fixed response found for story ID: {story_id}"); return None
        except Exception as e: logger.error(f"Error fetching fixed response for story ID {story_id}: {str(e)}"); return None

    def create_or_update_story_fixed_response(self, story_id, trigger_keyword, direct_response_text=None):
        logger.info(f"Creating/updating fixed response for story ID: {story_id}")
        try:
            # Use the model method. Note: No comment_response_text for stories.
            result = Story.set_fixed_response(story_id, trigger_keyword, direct_response_text)
            if result: logger.info(f"Fixed response C/U successful for story ID: {story_id}"); return True
            else: logger.warning(f"Failed to C/U fixed response for story ID: {story_id}"); return False
        except Exception as e: logger.error(f"Error C/U fixed response for story ID {story_id}: {str(e)}"); return False

    def delete_story_fixed_response(self, story_id):
        logger.info(f"Deleting fixed response for story ID: {story_id}")
        try:
            result = Story.delete_fixed_response(story_id) # Use the model method
            if result: logger.info(f"Fixed response deleted successfully for story ID: {story_id}"); return True
            else: logger.warning(f"Failed to delete fixed response for story ID: {story_id}"); return False
        except Exception as e: logger.error(f"Error deleting fixed response for story ID {story_id}: {str(e)}"); return False

    def set_story_admin_explanation(self, story_id, explanation):
        logger.info(f"Setting admin explanation for story ID: {story_id}")
        try:
            result = Story.set_admin_explanation(story_id, explanation) # Use the model method
            if result: logger.info(f"Admin explanation set for story ID: {story_id}"); return True
            else: logger.warning(f"Failed to set admin explanation for story ID: {story_id}"); return False
        except Exception as e: logger.error(f"Error setting admin explanation for story ID {story_id}: {str(e)}"); return False

    def get_story_admin_explanation(self, story_id):
        logger.info(f"Fetching admin explanation for story ID: {story_id}")
        try:
            explanation = Story.get_admin_explanation(story_id) # Use the model method
            if explanation is not None: logger.info(f"Admin explanation found for story ID: {story_id}"); return explanation
            else: logger.info(f"No admin explanation for story ID: {story_id}"); return None
        except Exception as e: logger.error(f"Error fetching admin explanation for story ID {story_id}: {str(e)}"); return None

    def remove_story_admin_explanation(self, story_id):
        logger.info(f"Removing admin explanation for story ID: {story_id}")
        try:
            result = Story.remove_admin_explanation(story_id) # Use the model method
            if result: logger.info(f"Admin explanation removed for story ID: {story_id}"); return True
            else: logger.warning(f"Failed to remove admin explanation for story ID: {story_id}"); return False
        except Exception as e: logger.error(f"Error removing admin explanation for story ID {story_id}: {str(e)}"); return False

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

