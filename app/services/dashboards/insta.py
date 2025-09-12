import logging
import streamlit as st
from ...models.post import Post
from ...models.story import Story
from ...models.client import Client
from ...models.product import Product
from ...models.user import User
from ...models.enums import MessageRole, UserStatus
from ..platforms.instagram import InstagramService
from ..AI.img_search import process_image
from ...config import Config
from datetime import datetime, timedelta, timezone
import requests
import pandas as pd
import plotly.express as px
from PIL import Image
import io

logging.basicConfig(
    handlers=[logging.FileHandler('logs.txt', encoding='utf-8'), logging.StreamHandler()],
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
#===============================================================================================================================
class AppConstants:
    ICONS = {
    "scraper": ":building_construction:",
    "scrape": ":rocket:",
    "update": ":arrows_counterclockwise:",
    "ai": ":robot_face:",
    "delete": ":wastebasket:",
    "add": ":heavy_plus_sign:",
    "success": ":white_check_mark:",
    "error": ":x:",
    "preview": ":eyes:",
    "brain": ":brain:",
    "chat": ":speech_balloon:",
    "connect": ":link:",
    "instagram": ":camera:",
    "post": ":newspaper:",
    "story": ":clapper:",   # changed from film_frames
    "paper_and_pen": ":memo:",
    "previous": ":arrow_left:",
    "next": ":arrow_right:",
    "label": ":label:",
    "save": ":floppy_disk:",
    "model": ":brain:",
    "folder": ":open_file_folder:",
    "dashboard": ":bar_chart:",
    "data": ":page_facing_up:",
    "login": ":key:",
    "logout": ":door:",
    "user": ":bust_in_silhouette:", 
    "controller": ":joystick:", 
    "default_user": "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_960_720.png",
    "admin": ":shield:",
    "fixed_message": ":pushpin:",
    
}

    AVATARS={
        "admin": "assets/icons/admin.png",
        "user": "assets/icons/user.png",
        "assistant": "assets/icons/assistant.png",
        "fixed_response": "assets/icons/fixed_response.png"
    }

    MESSAGES = {
        "scraping_start": "Scraping all products. This may take several minutes...",
        "update_start": "Checking for new products...",
        "processing_start": "Processing products - this may take several minutes..."
    }
class InstagramBackend:
    def __init__(self, client_username=None):
        self.client_username = client_username
        self.client_data = None
        if self.client_username:
            self.client_data = Client.get_by_username(self.client_username)
            if not self.client_data:
                logging.error(f"Client '{self.client_username}' not found")
                raise ValueError(f"Client '{self.client_username}' not found")
            if self.client_data.get('status') != 'active':
                logging.error(f"Client '{self.client_username}' is not active")
                raise ValueError(f"Client '{self.client_username}' is not active")
            logging.info(f"InstagramBackend initialized for client: {self.client_username}")

    def reload_main_app_memory(self):
        """Trigger the main app to reload all memory from the database."""
        logging.info("Triggering main app to reload memory from DB.")
        try:
            response = requests.post(
                Config.BASE_URL + "/hooshang_update/reload-memory",
                headers= {"Content-Type": "application/json",  "Authorization": f"Bearer {Config.VERIFY_TOKEN}" }
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

    def _validate_client_access(self, required_module=None):
        if not self.client_username:
            return True
        if not self.client_data:
            raise ValueError("Client data not loaded")
        if self.client_data.get('status') != 'active':
            raise ValueError(f"Client '{self.client_username}' is not active")
        if required_module:
            if not Client.is_module_enabled(self.client_username, required_module):
                raise ValueError(f"Module '{required_module}' is not enabled for client '{self.client_username}'")
        return True

    def get_products(self):
            """Wrapper for Product model's get_all method."""
            self._validate_client_access()
            try:
                logging.info(f"Fetching all products for client: {self.client_username or 'admin'}")
                return Product.get_all(client_username=self.client_username)
            except Exception as e:
                logging.error(f"Error fetching products for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
                return []

    def _process_media_for_labeling(self, item_id, media_url, thumbnail_url, item_type="post"):
        if not media_url and not thumbnail_url:
            logging.warning(f"{item_type.capitalize()} ID {item_id} has no media URL or thumbnail URL.")
            return None, "No image URL available"
        url_to_use = thumbnail_url if thumbnail_url else media_url
        logging.info(f"Downloading image for {item_type} ID {item_id} from {url_to_use}")
        try:
            response = requests.get(url_to_use, stream=True, timeout=20)
            response.raise_for_status()
            image_bytes = response.content
            if not image_bytes:
                return None, "Downloaded image is empty"
            image_stream = io.BytesIO(image_bytes)
            pil_image = Image.open(image_stream)
            predicted_label = process_image(pil_image, self.client_username)
            if not predicted_label:
                logging.info(f"Vision model couldn't find a label for {item_type} ID {item_id}")
                return None, "Model couldn't determine a label"
            return predicted_label, None
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to download image for {item_type} {item_id}: {str(e)}")
            return None, f"Failed to download image: {str(e)}"
        except Image.UnidentifiedImageError:
            logging.error(f"Could not identify image for {item_type} {item_id} (not a valid image format or corrupted). URL: {url_to_use}")
            return None, "Invalid image format or corrupted file."
        except Exception as e:
            logging.error(f"Error processing image for {item_type} {item_id}: {str(e)}")
            return None, f"Error processing image: {str(e)}"

    # --- Post Methods ---
    def fetch_instagram_posts(self):
        self._validate_client_access()
        logging.info(f"Fetching Instagram posts for client: {self.client_username or 'admin'}")
        try:
            result = InstagramService.get_posts(client_username=self.client_username)
            if result:
                logging.info(f"Instagram posts fetched/updated successfully for client: {self.client_username or 'admin'}")
                reload_success = self.reload_main_app_memory()
                if reload_success:  
                    return result
                else:
                    logging.ERROR('Failed to reload_main_app_memory after fetching Instagram posts')
                    return False
            else:
                logging.warning(f"Failed to fetch/update Instagram posts for client: {self.client_username or 'admin'}")
            return result
        except Exception as e:
            logging.error(f"Failed to fetch Instagram posts for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return False

    def get_posts(self):
        self._validate_client_access()
        logging.info(f"Fetching stored Instagram posts for client: {self.client_username or 'admin'}")
        try:
            posts = Post.get_all(client_username=self.client_username)
            post_data = [
                {"id": post.get('id'), "media_url": post.get('media_url'), "thumbnail_url": post.get('thumbnail_url'),
                 "caption": post.get('caption'), "label": post.get('label', ''), "media_type": post.get('media_type')}
                for post in posts if post.get('id')
            ]
            logging.info(f"Successfully fetched {len(post_data)} Instagram posts for client: {self.client_username or 'admin'}")
            return post_data
        except Exception as e:
            logging.error(f"Error fetching stored Instagram posts for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return []

    def set_post_label(self, post_id, label):
        self._validate_client_access('vision')
        logging.info(f"Setting label '{label}' for post ID: {post_id} for client: {self.client_username or 'admin'}")
        if not post_id:
            logging.error("Cannot set post label: post_id is missing.")
            return False
        try:
            success = Post.set_label(post_id, label, client_username=self.client_username)
            if success:
                logging.info(f"Label update successful for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else:
                logging.warning(f"Could not set label for post ID {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e:
            logging.error(f"Error setting label for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return False

    def remove_post_label(self, post_id):
        self._validate_client_access('vision')
        logging.info(f"Removing label for post ID: {post_id} for client: {self.client_username or 'admin'}")
        if not post_id:
            logging.error("Cannot remove post label: post_id is missing.")
            return False
        try:
            success = Post.remove_label(post_id, client_username=self.client_username)
            if success:
                logging.info(f"Label removed for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else:
                logging.warning(f"Could not remove label for post ID {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e:
            logging.error(f"Error removing label for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return False

    def unset_all_post_labels(self):
        self._validate_client_access('vision')
        logging.info(f"Unsetting labels from all posts for client: {self.client_username or 'admin'}")
        try:
            updated_count = Post.unset_all_labels(client_username=self.client_username)
            logging.info(f"Successfully unset labels from {updated_count} posts for client: {self.client_username or 'admin'}")
            return updated_count
        except Exception as e:
            logging.error(f"Error unsetting all post labels for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return 0

    def set_single_post_label_by_model(self, post_id):
        self._validate_client_access('vision')
        logging.info(f"Processing post ID {post_id} for automatic labeling for client: {self.client_username or 'admin'}")
        try:
            post = Post.get_by_instagram_id(post_id, client_username=self.client_username)
            if not post:
                logging.warning(f"Post with ID {post_id} not found for client: {self.client_username or 'admin'}")
                return {"success": False, "message": "Post not found"}
            predicted_label, error_msg = self._process_media_for_labeling(post_id, post.get('media_url'), post.get('thumbnail_url'), "post")
            if error_msg:
                return {"success": False, "message": error_msg}
            if predicted_label:
                label_set_success = self.set_post_label(post_id, predicted_label)
                if label_set_success:
                    logging.info(f"Post ID {post_id} automatically labeled as '{predicted_label}' for client: {self.client_username or 'admin'}")
                    return {"success": True, "label": predicted_label}
                else:
                    return {"success": False, "message": "Failed to set label in database"}
            return {"success": False, "message": "Model couldn't determine a label"}
        except Exception as e:
            logging.error(f"Error in set_single_post_label_by_model for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def set_post_labels_by_model(self):
        self._validate_client_access('vision')
        logging.info(f"Starting automatic labeling of posts by model for client: {self.client_username or 'admin'}")
        processed_count, labeled_count, errors = 0, 0, []
        all_posts = Post.get_all(client_username=self.client_username)
        if not all_posts:
            return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'No posts found.'}
        unlabeled_posts = [p for p in all_posts if not p.get('label')]
        logging.info(f"Found {len(unlabeled_posts)} posts without labels for client: {self.client_username or 'admin'}")
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
        logging.info(message)
        return {'success': not errors, 'processed': processed_count, 'labeled': labeled_count, 'message': message, 'errors': errors}

    def download_post_labels(self):
        self._validate_client_access()
        logging.info(f"Preparing posts organized by labels for download for client: {self.client_username or 'admin'}")
        try:
            posts = Post.get_all(client_username=self.client_username)
            if not posts: return {}
            labeled_posts = {}
            for post in posts:
                label = post.get('label', '').strip()
                if not label: continue
                image_url = post.get('thumbnail_url') or post.get('media_url')
                if image_url:
                    if label not in labeled_posts: labeled_posts[label] = []
                    labeled_posts[label].append(image_url)
                children = post.get('children', [])
                if children:
                    for child in children:
                        child_url = child.get('thumbnail_url') or child.get('media_url')
                        if child_url:
                            if label not in labeled_posts: labeled_posts[label] = []
                            labeled_posts[label].append(child_url)
            logging.info(f"Successfully prepared posts by label, found {len(labeled_posts)} unique labels for client: {self.client_username or 'admin'}")
            return labeled_posts
        except Exception as e:
            logging.error(f"Error preparing post labels for download: {str(e)}", exc_info=True)
            return {"error": str(e)}

    def get_post_fixed_responses(self, post_id):
        self._validate_client_access('fixed_response')
        logging.info(f"Fetching fixed responses for post ID: {post_id} for client: {self.client_username or 'admin'}")
        try:
            responses = Post.get_fixed_responses(post_id, client_username=self.client_username)
            if responses:
                logging.info(f"Fixed responses found for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return responses
            else:
                logging.info(f"No fixed responses found for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return []
        except Exception as e:
            logging.error(f"Error fetching fixed responses for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return []

    def create_or_update_post_fixed_response(self, post_id, trigger_keyword, comment_response_text=None, direct_response_text=None):
        self._validate_client_access('fixed_response')
        logging.info(f"Adding/updating fixed response for post ID: {post_id} with trigger: {trigger_keyword} for client: {self.client_username or 'admin'}")
        try:
            result = Post.add_fixed_response(post_id, trigger_keyword, self.client_username, comment_response_text, direct_response_text)
            if result:
                logging.info(f"Fixed response added/updated successful for post ID: {post_id} for client: {self.client_username or 'admin'}")
                reload_success = self.reload_main_app_memory()
                if reload_success:  
                    return True
                else:
                    logging.ERROR('Failed to reload_main_app_memory after adding/updating fixed response')
                    return False   
            else:
                logging.warning(f"Failed to add/update fixed response for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e:
            logging.error(f"Error adding/updating fixed response for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return False

    def delete_post_fixed_response(self, post_id, trigger_keyword):
        self._validate_client_access('fixed_response')
        logging.info(f"Deleting fixed response for post ID: {post_id} with trigger: {trigger_keyword} for client: {self.client_username or 'admin'}")
        try:
            result = Post.delete_fixed_response(post_id, trigger_keyword, client_username=self.client_username)
            if result:
                logging.info(f"Fixed response deleted successfully for post ID: {post_id} for client: {self.client_username or 'admin'}")
                reload_success = self.reload_main_app_memory()
                if reload_success:  
                    return True
                else:
                    logging.ERROR('Failed to reload_main_app_memory after deleting fixed response')
                    return False
            else:
                logging.warning(f"Failed to delete fixed response for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e:
            logging.error(f"Error deleting fixed response for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return False

    def set_post_admin_explanation(self, post_id, explanation):
        self._validate_client_access()
        logging.info(f"Setting admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
        try:
            result = Post.set_admin_explanation(post_id, explanation, client_username=self.client_username)
            if result:
                logging.info(f"Admin explanation set for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else:
                logging.warning(f"Failed to set admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e:
            logging.error(f"Error setting admin explanation for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return False

    def get_post_admin_explanation(self, post_id):
        self._validate_client_access()
        logging.info(f"Fetching admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
        try:
            explanation = Post.get_admin_explanation(post_id, client_username=self.client_username)
            if explanation is not None:
                logging.info(f"Admin explanation found for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return explanation
            else:
                logging.info(f"No admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return None
        except Exception as e:
            logging.error(f"Error fetching admin explanation for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return None

    def remove_post_admin_explanation(self, post_id):
        self._validate_client_access()
        logging.info(f"Removing admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
        try:
            result = Post.remove_admin_explanation(post_id, client_username=self.client_username)
            if result:
                logging.info(f"Admin explanation removed for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return True
            else:
                logging.warning(f"Failed to remove admin explanation for post ID: {post_id} for client: {self.client_username or 'admin'}")
                return False
        except Exception as e:
            logging.error(f"Error removing admin explanation for post ID {post_id} for client {self.client_username or 'admin'}: {str(e)}")
            return False

    # --- Story Methods ---
    def fetch_instagram_stories(self):
        self._validate_client_access()
        logging.info(f"Fetching Instagram stories for client: {self.client_username or 'admin'}")
        try:
            result = InstagramService.get_stories(client_username=self.client_username)
            if result:
                logging.info(f"Instagram stories fetched/updated successfully for client: {self.client_username or 'admin'}")
                reload_success = self.reload_main_app_memory()
                if reload_success:  
                    return result
                else:
                    logging.ERROR('Failed to reload_main_app_memory after fetching Instagram stories')
                    return False
            else:
                logging.warning(f"Failed to fetch/update Instagram stories for client: {self.client_username or 'admin'}")
            return result
        except Exception as e:
            logging.error(f"Failed to fetch Instagram stories for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return False

    def get_stories(self):
        self._validate_client_access()
        logging.info(f"Fetching stored Instagram stories for client: {self.client_username or 'admin'}")
        try:
            stories = Story.get_all(client_username=self.client_username)
            story_data = [
                {"id": story.get('id'), "media_url": story.get('media_url'), "thumbnail_url": story.get('thumbnail_url'),
                 "caption": story.get('caption'), "label": story.get('label', ''), "media_type": story.get('media_type')}
                for story in stories if story.get('id')
            ]
            logging.info(f"Successfully fetched {len(story_data)} Instagram stories from DB for client: {self.client_username or 'admin'}")
            return story_data
        except Exception as e:
            logging.error(f"Error fetching stored Instagram stories for client {self.client_username or 'admin'}: {str(e)}", exc_info=True)
            return []

    def set_story_label(self, story_id, label):
        self._validate_client_access('vision')
        logging.info(f"Setting label '{label}' for story ID: {story_id} for client: {self.client_username or 'admin'}")
        if not story_id:
            logging.error("Cannot set story label: story_id is missing.")
            return False
        try:
            success = Story.set_label(story_id, label, client_username=self.client_username)
            if success:
                logging.info(f"Label update successful for story ID: {story_id}"); return True
            else:
                logging.warning(f"Could not set label for story ID {story_id}"); return False
        except Exception as e:
            logging.error(f"Error setting label for story ID {story_id}: {str(e)}", exc_info=True); return False

    def remove_story_label(self, story_id):
        self._validate_client_access('vision')
        logging.info(f"Removing label for story ID: {story_id} for client: {self.client_username or 'admin'}")
        if not story_id:
            logging.error("Cannot remove story label: story_id is missing."); return False
        try:
            success = Story.remove_label(story_id, client_username=self.client_username)
            if success: logging.info(f"Label removed for story ID: {story_id}"); return True
            else: logging.warning(f"Could not remove label for story ID {story_id}"); return False
        except Exception as e: logging.error(f"Error removing label for story ID {story_id}: {str(e)}", exc_info=True); return False

    def unset_all_story_labels(self):
        self._validate_client_access('vision')
        logging.info(f"Unsetting labels from all stories for client: {self.client_username or 'admin'}")
        try:
            updated_count = Story.unset_all_labels(client_username=self.client_username)
            logging.info(f"Successfully unset labels from {updated_count} stories for client: {self.client_username or 'admin'}")
            return updated_count
        except Exception as e: logging.error(f"Error unsetting all story labels: {str(e)}", exc_info=True); return 0

    def set_single_story_label_by_model(self, story_id):
        self._validate_client_access('vision')
        logging.info(f"Processing story ID {story_id} for automatic labeling for client: {self.client_username or 'admin'}")
        try:
            story = Story.get_by_instagram_id(story_id, client_username=self.client_username)
            if not story:
                logging.warning(f"Story with ID {story_id} not found."); return {"success": False, "message": "Story not found"}
            media_type = story.get('media_type', '').upper()
            media_url = story.get('media_url')
            thumbnail_url = story.get('thumbnail_url')
            if media_type == 'VIDEO' and not thumbnail_url:
                logging.info(f"Story ID {story_id} is a video without a thumbnail. Skipping AI labeling.")
                return {"success": False, "message": "Cannot label video without thumbnail."}
            predicted_label, error_msg = self._process_media_for_labeling(story_id, media_url, thumbnail_url, "story")
            if error_msg:
                return {"success": False, "message": error_msg}
            if predicted_label:
                label_set_success = self.set_story_label(story_id, predicted_label)
                if label_set_success:
                    logging.info(f"Story ID {story_id} automatically labeled as '{predicted_label}'")
                    return {"success": True, "label": predicted_label}
                else:
                    return {"success": False, "message": "Failed to set label in database"}
            return {"success": False, "message": "Model couldn't determine a label"}
        except Exception as e:
            logging.error(f"Error in set_single_story_label_by_model for story ID {story_id}: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def set_story_labels_by_model(self):
        self._validate_client_access('vision')
        logging.info(f"Starting automatic labeling of stories by model for client: {self.client_username or 'admin'}")
        processed_count, labeled_count, errors = 0, 0, []
        all_stories = Story.get_all(client_username=self.client_username)
        if not all_stories:
            return {'success': True, 'processed': 0, 'labeled': 0, 'message': 'No stories found.'}
        unlabeled_stories = [s for s in all_stories if not s.get('label')]
        logging.info(f"Found {len(unlabeled_stories)} stories without labels for client: {self.client_username or 'admin'}")
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
        logging.info(message)
        return {'success': not errors, 'processed': processed_count, 'labeled': labeled_count, 'message': message, 'errors': errors}

    def download_story_labels(self):
        self._validate_client_access()
        logging.info(f"Preparing stories organized by labels for download for client: {self.client_username or 'admin'}")
        try:
            stories = Story.get_all(client_username=self.client_username)
            if not stories: return {}
            labeled_stories = {}
            for story in stories:
                label = story.get('label', '').strip()
                if not label: continue
                image_url = story.get('thumbnail_url') or story.get('media_url')
                if not image_url: continue
                if label not in labeled_stories: labeled_stories[label] = []
                labeled_stories[label].append(image_url)
            logging.info(f"Successfully prepared stories by label, found {len(labeled_stories)} unique labels for client: {self.client_username or 'admin'}")
            return labeled_stories
        except Exception as e:
            logging.error(f"Error preparing story labels for download: {str(e)}", exc_info=True)
            return {"error": str(e)}

    def get_story_fixed_responses(self, story_id):
        self._validate_client_access('fixed_response')
        logging.info(f"Fetching fixed responses for story ID: {story_id} for client: {self.client_username or 'admin'}")
        try:
            responses = Story.get_fixed_responses(story_id, client_username=self.client_username)
            if responses: logging.info(f"Fixed responses found for story ID: {story_id}"); return responses
            else: logging.info(f"No fixed responses found for story ID: {story_id}"); return []
        except Exception as e: logging.error(f"Error fetching fixed responses for story ID {story_id}: {str(e)}"); return []

    def create_or_update_story_fixed_response(self, story_id, trigger_keyword, direct_response_text=None):
        self._validate_client_access('fixed_response')
        logging.info(f"Adding/updating fixed response for story ID: {story_id} with trigger: {trigger_keyword} for client: {self.client_username or 'admin'}")
        try:
            result = Story.add_fixed_response(
                story_id,
                trigger_keyword,
                client_username=self.client_username,
                direct_response_text=direct_response_text
            )
            if result: 
                logging.info(f"Fixed response added/updated successful for story ID: {story_id}")
                reload_success = self.reload_main_app_memory()
                if reload_success:  
                    return True
                else:
                    logging.warning(f"Failed to reload main app memory for client: {self.client_username or 'admin'}")
                    return False
            else: logging.warning(f"Failed to add/update fixed response for story ID: {story_id}"); return False
        except Exception as e: logging.error(f"Error adding/updating fixed response for story ID {story_id}: {str(e)}"); return False

    def delete_story_fixed_response(self, story_id, trigger_keyword):
        self._validate_client_access('fixed_response')
        logging.info(f"Deleting fixed response for story ID: {story_id} with trigger: {trigger_keyword} for client: {self.client_username or 'admin'}")
        try:
            result = Story.delete_fixed_response(story_id, trigger_keyword, client_username=self.client_username)
            if result:
                logging.info(f"Fixed response deleted successfully for story ID: {story_id}")
                reload_success = self.reload_main_app_memory()
                if reload_success:  
                    return True
                else:
                    logging.warning(f"Failed to reload main app memory for client: {self.client_username or 'admin'}")
                    return False
            else: logging.warning(f"Failed to delete fixed response for story ID: {story_id}"); return False
        except Exception as e: logging.error(f"Error deleting fixed response for story ID {story_id}: {str(e)}"); return False

    def set_story_admin_explanation(self, story_id, explanation):
        self._validate_client_access()
        logging.info(f"Setting admin explanation for story ID: {story_id} for client: {self.client_username or 'admin'}")
        try:
            result = Story.set_admin_explanation(story_id, explanation, client_username=self.client_username)
            if result: logging.info(f"Admin explanation set for story ID: {story_id}"); return True
            else: logging.warning(f"Failed to set admin explanation for story ID: {story_id}"); return False
        except Exception as e: logging.error(f"Error setting admin explanation for story ID {story_id}: {str(e)}"); return False

    def get_story_admin_explanation(self, story_id):
        self._validate_client_access()
        logging.info(f"Fetching admin explanation for story ID: {story_id} for client: {self.client_username or 'admin'}")
        try:
            explanation = Story.get_admin_explanation(story_id, client_username=self.client_username)
            if explanation is not None: logging.info(f"Admin explanation found for story ID: {story_id}"); return explanation
            else: logging.info(f"No admin explanation for story ID: {story_id}"); return None
        except Exception as e: logging.error(f"Error fetching admin explanation for story ID {story_id}: {str(e)}"); return None

    def remove_story_admin_explanation(self, story_id):
        self._validate_client_access()
        logging.info(f"Removing admin explanation for story ID: {story_id} for client: {self.client_username or 'admin'}")
        try:
            result = Story.remove_admin_explanation(story_id, client_username=self.client_username)
            if result: logging.info(f"Admin explanation removed for story ID: {story_id}"); return True
            else: logging.warning(f"Failed to remove admin explanation for story ID: {story_id}"); return False
        except Exception as e: logging.error(f"Error removing admin explanation for story ID {story_id}: {str(e)}"); return False

    def get_all_users(self):
        """Wrapper to get all Instagram users for the client."""
        return User.get_users_by_platform_for_client("instagram", self.client_username)

    def get_user_messages(self, user_id):
        """Wrapper for User model's get_user_messages method."""
        return User.get_user_messages(user_id, client_username=self.client_username, limit=100)
    
    def get_user_by_id(self, user_id):
        """Wrapper for User model's get_by_id method."""
        return User.get_by_id(user_id, client_username=self.client_username)

    def get_message_statistics_by_role_within_timeframe_by_platform(self, time_frame, start_datetime, end_datetime, platform):
        """Wrapper for User model's message statistics method."""
        return User.get_message_statistics_by_role_within_timeframe_by_platform(
            time_frame, start_datetime, end_datetime, platform, self.client_username
        )

    def get_user_status_counts_within_timeframe_by_platform(self, start_datetime, end_datetime, platform):
        """Wrapper for User model's user status counts method."""
        return User.get_user_status_counts_within_timeframe_by_platform(
            start_datetime, end_datetime, platform, self.client_username
        )

    def get_total_users_count_within_timeframe_by_platform(self, start_datetime, end_datetime, platform):
        """Wrapper for User model's total user count method."""
        return User.get_total_users_count_within_timeframe_by_platform(
            start_datetime, end_datetime, platform, self.client_username
        )

    def get_user_status_counts_by_platform(self, platform):
        """Wrapper for User model's user status counts method for all time."""
        return User.get_user_status_counts_by_platform(platform, self.client_username)

    def get_total_users_count_by_platform(self, platform):
        """Wrapper for User model's total user count method for all time."""
        return User.get_total_users_count_by_platform(platform, self.client_username)
    
    def get_paginated_users(self, page=1, limit=25, status_filter=None):
        """
        Wrapper to get a paginated and filtered list of Instagram users for the client.
        """
        return User.get_paginated_users_by_platform(
            platform="instagram",
            client_username=self.client_username,
            page=page,
            limit=limit,
            status_filter=status_filter
        )
    
#===============================================================================================================================
class BaseSection:
    """Base class for UI sections"""
    def __init__(self, client_username=None):
        self.backend = InstagramBackend(client_username=client_username)
        self.const = AppConstants()
#===============================================================================================================================
class InstagramUI(BaseSection):
    """Handles Instagram-related functionality including posts, stories"""
    def __init__(self, client_username=None):
        super().__init__(client_username)
        if 'custom_labels' not in st.session_state:
            st.session_state['custom_labels'] = []
        if 'post_page' not in st.session_state:
            st.session_state['post_page'] = 0
        if 'posts_per_page' not in st.session_state:
            st.session_state['posts_per_page'] = 8
        if 'post_filter' not in st.session_state:
            st.session_state['post_filter'] = "All"
        if 'story_page' not in st.session_state:
            st.session_state['story_page'] = 0
        if 'stories_per_page' not in st.session_state:
            st.session_state['stories_per_page'] = 6
        if 'selected_story_id' not in st.session_state:
            st.session_state['selected_story_id'] = None
        if 'story_filter' not in st.session_state:
            st.session_state['story_filter'] = "All"
        if 'selected_instagram_user' not in st.session_state:
            st.session_state.selected_instagram_user = None
        if 'selected_instagram_user_data' not in st.session_state:
            st.session_state.selected_instagram_user_data = None

    def render(self):
        self._render_controller_panel()
        st.write("---")
        
        posts_tab, stories_tab, statistics_tab, chat_tab = st.tabs([
            f"{self.const.ICONS['post']} Posts",
            f"{self.const.ICONS['story']} Stories",
            f"{self.const.ICONS['dashboard']} Statistics",
            f"{self.const.ICONS['chat']} Chat"
        ])

        with posts_tab:
            self._render_posts_tab()

        with stories_tab:
            self._render_stories_tab()
            
        with statistics_tab:
            self._render_statistics_tab()

        with chat_tab:
            self._render_chat_tab()

        st.write("---")

    def _render_statistics_tab(self):
        """Renders the combined statistics tab for messages and users."""
        # --- Centralized Controls ---
        col1, col2, col3 = st.columns([2, 2, 1])
        key_suffix = "instagram_stats"
        with col1:
            time_frame = st.selectbox("Time Frame", options=["daily", "hourly"], index=1, key=f"time_frame_{key_suffix}")
        with col2:
            duration_options = {"1 day": 1, "7 days": 7, "1 month": 30, "3 months": 90, "All time": 0}
            selected_duration = st.selectbox("Duration", options=list(duration_options.keys()), index=0, key=f"duration_{key_suffix}")
            days_back = duration_options[selected_duration]
        with col3:
            st.markdown("_")
            if st.button(f"{self.const.ICONS['update']} Refresh", key=f"refresh_{key_suffix}", width='stretch'):
                st.rerun()
        
        end_datetime = datetime.now(timezone.utc)
        start_datetime = end_datetime - timedelta(days=days_back)

        st.write("---")
        self._render_message_analytics(time_frame, start_datetime, end_datetime, days_back)
        st.write("---")
        self._render_user_statistics(start_datetime, end_datetime, days_back)

    def _render_chat_tab(self):
        """Renders the chat history and interaction tab."""
        try:
            user_list_col, chat_display_col = st.columns([1, 2])
            with user_list_col:
                self._render_user_sidebar()
            with chat_display_col:
                if st.session_state.selected_instagram_user and st.session_state.selected_instagram_user_data:
                    self._display_user_info(st.session_state.selected_instagram_user_data)
                    self._display_chat_messages(st.session_state.selected_instagram_user_data)
                else:
                    with st.container(border=True, height=700):
                        st.info("Select a conversation from the list to view the chat history.")
        except Exception as e:
            st.error(f"Error rendering chat history: {str(e)}")
    def _render_user_sidebar(self):
        """
        Renders an efficient, paginated, and filterable sidebar for the chat tab,
        with display name logic matching the specified preference order.
        """
        with st.container(border=True):
            # --- 1. Initialize Session State for Pagination and Filtering ---
            if 'chat_page' not in st.session_state:
                st.session_state.chat_page = 1
            if 'chat_status_filter' not in st.session_state:
                st.session_state.chat_status_filter = "All"

            # --- 2. Add Filtering Controls ---
            st.markdown("**Filter by Status**")
            status_options = ["All"] + [status.value for status in UserStatus]
            
            def on_filter_change():
                st.session_state.chat_page = 1

            selected_status = st.selectbox(
                "User Status",
                options=status_options,
                key='chat_status_filter',
                on_change=on_filter_change,
                label_visibility="collapsed"
            )
            
            # --- 3. Fetch Paginated Data from Backend ---
            status_to_query = None if selected_status == "All" else selected_status
            
            try:
                paginated_data = self.backend.get_paginated_users(
                    page=st.session_state.chat_page,
                    limit=25,
                    status_filter=status_to_query
                )
                users = paginated_data.get("users", [])
                total_users = paginated_data.get("total_count", 0)
                total_pages = paginated_data.get("total_pages", 1)

                if not users:
                    st.info("No Instagram users found with the selected filter.")
                    return

                # --- 4. Display User List ---
                with st.container(height=550):
                    for user in users:
                        user_id = user.get("user_id")
                        # Safeguard: although you expect user_id to always exist,
                        # this prevents any future errors if a bad record is ever created.
                        if not user_id:
                            continue

                        # ============================ REFINED LOGIC IS HERE ============================
                        # Build the full name from parts that actually exist (are not None or empty).
                        full_name_parts = [name for name in [user.get("first_name"), user.get("last_name")] if name]
                        full_name = " ".join(full_name_parts)

                        # Apply the display name logic in the specified order of preference.
                        # The `or` operator in Python elegantly handles this: it returns the first truthy value.
                        display_name = user.get("username") or full_name or user_id
                        # ===============================================================================

                        entry = st.container(border=True)
                        col1, col2 = entry.columns([1, 4])
                        
                        profile_pic = self.const.ICONS["default_user"]
                        col1.image(profile_pic, width=40, clamp=True)

                        if col2.button(display_name, key=f"insta_user_select_{user_id}", width='stretch'):
                            st.session_state.selected_instagram_user = user_id
                            st.session_state.selected_instagram_user_data = self.backend.get_user_by_id(user_id)
                            st.rerun()
                
                # --- 5. Add Pagination Controls ---
                st.write("---")
                nav_col1, nav_col2, nav_col3 = st.columns([2, 3, 2])

                with nav_col1:
                    if st.button(f"{self.const.ICONS['previous']} Prev", width='stretch', disabled=(st.session_state.chat_page <= 1)):
                        st.session_state.chat_page -= 1
                        st.rerun()
                
                with nav_col2:
                    st.markdown(f"<div style='text-align: center;'>Page {st.session_state.chat_page} of {total_pages}</div>", unsafe_allow_html=True)
                    st.caption(f"Total Users: {total_users}")

                with nav_col3:
                    if st.button(f"Next {self.const.ICONS['next']}", width='stretch', disabled=(st.session_state.chat_page >= total_pages)):
                        st.session_state.chat_page += 1
                        st.rerun()

            except Exception as e:
                st.error(f"Failed to load users: {e}")
    
    def _display_user_info(self, user_data):
        """Displays key information for the selected user."""
        with st.container(border=True):
            username = user_data.get("username", "N/A")
            full_name = user_data.get("full_name", "N/A")
            followers = user_data.get("follower_count", "N/A")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Username", username)
            col2.metric("Full Name", full_name)
            col3.metric("Followers", followers)
            
    def _display_chat_messages(self, user_data):
        """Displays the chat history and a message input box for the selected user."""
        display_name = user_data.get("username") or "User"
            
        chat_container = st.container(height=550, border=True)
        with chat_container:
                st.markdown(f"**Chat with {display_name}**")
                messages = self.backend.get_user_messages(user_data["user_id"])
                
                if not messages:
                    st.warning("No messages found for this user.")
                else:
                    default_avatar = "💬" 

                    for msg in messages:
                        role = msg.get("role")
                        
                        alignment = "user" if role == MessageRole.USER.value else "assistant"
                        
                        avatar = self.const.AVATARS.get(role, default_avatar)
                        
                        with st.chat_message(alignment, avatar=avatar):
                            st.markdown(msg.get("text", "*No text content*"))
                            
                            if msg.get("media_url"):
                                st.image(msg["media_url"])
                            
                            timestamp = msg.get("timestamp")
                            if timestamp:
                                st.caption(timestamp.astimezone().strftime('%Y-%m-%d %H:%M'))

        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            text_input = col1.text_input("Type a message...", key=f"insta_chat_input_{user_data['user_id']}", label_visibility="collapsed")
            send_button = col2.button("Send", key=f"insta_send_button_{user_data['user_id']}", use_container_width=True)

            if send_button and text_input:
                user_id = user_data["user_id"]
                mid = InstagramService.send_message(user_id, text_input, self.backend.client_username)
                if mid:
                    message_doc = User.create_message_document(
                        text=text_input,
                        role=MessageRole.ADMIN.value,
                        mid= mid,
                        timestamp=datetime.now(timezone.utc)
                    )
                    User.add_direct_message(user_id, message_doc, self.backend.client_username)
                    User.update_status(user_id, UserStatus.ADMIN_REPLIED.value, self.backend.client_username)
                    st.success("Message sent and user status updated!")
                    st.rerun()
                else:
                    st.error("Failed to send message.")

    def _render_controller_panel(self):
            """Render Instagram platform controller panel"""
            st.subheader(f"{self.const.ICONS.get('instagram', '')} Instagram Controller")
            
            try:
                from ...services.dashboards.ui import validate_client_access
                validate_client_access(self.backend.client_username)
                
                # Get platform configuration
                platform_config = Client.get_client_platforms_config(self.backend.client_username)
                instagram_config = platform_config.get('instagram', {})
                
                # Platform enable toggle
                platform_enabled = instagram_config.get('enabled', False)
                new_platform_enabled = st.toggle(
                    "Enable Instagram Platform", 
                    value=platform_enabled, 
                    key="instagram_platform_enable"
                )
                
                if new_platform_enabled != platform_enabled:
                    if Client.update_platform_enabled_status(self.backend.client_username, 'instagram', new_platform_enabled):
                        st.success(f"Instagram platform {'enabled' if new_platform_enabled else 'disabled'} successfully")
                        st.rerun()
                    else:
                        st.error("Failed to update Instagram platform status")
                
                # Module toggles (only show if platform is enabled)
                if new_platform_enabled:
                    st.write("### Module Controls")
                    modules = instagram_config.get('modules', {})
                    
                    # Create columns for module toggles
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Fixed Response toggle
                        fixed_response_enabled = modules.get('fixed_response', {}).get('enabled', False)
                        new_fixed_response = st.toggle(
                            "Fixed Response", 
                            value=fixed_response_enabled, 
                            key="instagram_fixed_response"
                        )
                        
                        if new_fixed_response != fixed_response_enabled:
                            if Client.update_module_status(self.backend.client_username, 'instagram', 'fixed_response', new_fixed_response):
                                st.success(f"Fixed Response {'enabled' if new_fixed_response else 'disabled'}")
                                st.rerun()
                            else:
                                st.error("Failed to update Fixed Response")
                        
                        # Comment Assist toggle
                        comment_assist_enabled = modules.get('comment_assist', {}).get('enabled', False)
                        new_comment_assist = st.toggle(
                            "Comment Assist", 
                            value=comment_assist_enabled, 
                            key="instagram_comment_assist"
                        )
                        
                        if new_comment_assist != comment_assist_enabled:
                            if Client.update_module_status(self.backend.client_username, 'instagram', 'comment_assist', new_comment_assist):
                                st.success(f"Comment Assist {'enabled' if new_comment_assist else 'disabled'}")
                                st.rerun()
                            else:
                                st.error("Failed to update Comment Assist")
                    
                    with col2:
                        # DM Assist toggle
                        dm_assist_enabled = modules.get('dm_assist', {}).get('enabled', False)
                        new_dm_assist = st.toggle(
                            "DM Assist", 
                            value=dm_assist_enabled, 
                            key="instagram_dm_assist"
                        )
                        
                        if new_dm_assist != dm_assist_enabled:
                            if Client.update_module_status(self.backend.client_username, 'instagram', 'dm_assist', new_dm_assist):
                                st.success(f"DM Assist {'enabled' if new_dm_assist else 'disabled'}")
                                st.rerun()
                            else:
                                st.error("Failed to update DM Assist")
                        
                        # Vision toggle
                        vision_enabled = modules.get('vision', {}).get('enabled', False)
                        new_vision = st.toggle(
                            "Vision", 
                            value=vision_enabled, 
                            key="instagram_vision"
                        )
                        
                        if new_vision != vision_enabled:
                            if Client.update_module_status(self.backend.client_username, 'instagram', 'vision', new_vision):
                                st.success(f"Vision {'enabled' if new_vision else 'disabled'}")
                                st.rerun()
                            else:
                                st.error("Failed to update Vision")
                else:
                    st.info("Enable the Instagram platform to access module controls.")
                    
            except ValueError as e:
                st.error(f"Access denied: {str(e)}")
            except Exception as e:
                st.error(f"Error rendering controller panel: {str(e)}")

    def _render_message_analytics(self, time_frame, start_datetime, end_datetime, days_back):
        with st.container(border=True):
            if days_back == 0:
                st.info("Please select a specific duration (e.g., '1 day', '7 days') to view message analytics.")
                return
            
            try:
                message_stats = self.backend.get_message_statistics_by_role_within_timeframe_by_platform(time_frame, start_datetime, end_datetime, "instagram")
                
                if not message_stats:
                    st.info("No message data available for the selected time period.")
                    return

                df = pd.DataFrame(
                    [{"Date": date_str, "Role": role, "Count": count} for date_str, roles in message_stats.items() for role, count in roles.items()]
                )
                if df.empty:
                    st.info("No message data to display.")
                    return
                
                summary_counts = df.groupby('Role')['Count'].sum()
                
                user_msgs = int(summary_counts.get('user', 0))
                assistant_msgs = int(summary_counts.get('assistant', 0))
                admin_msgs = int(summary_counts.get('admin', 0))
                fixed_responses = int(summary_counts.get('fixed_response', 0))
                
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("User Messages", user_msgs)
                m_col2.metric("Assistant Messages", assistant_msgs)
                m_col3.metric("Admin Messages", admin_msgs)
                m_col4.metric("Fixed Responses", fixed_responses)
                st.write("---")
                
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.sort_values('Date')

                fig = px.bar(df, x='Date', y='Count', color='Role', title='Direct Messages by Role', color_discrete_map={'user': '#1f77b4', 'assistant': '#ff7f0e', 'admin': '#2ca02c', 'fixed_response': '#d62728'})
                
                if time_frame == "hourly":
                    fig.update_xaxes(tickformat="%Y-%m-%d %H:%M", title_text="Time")
                else:
                    fig.update_xaxes(tickformat="%Y-%m-%d", title_text="Date")
                
                fig.update_yaxes(title_text="Number of Messages")
                
                st.plotly_chart(fig, width='stretch')
                
            except Exception as e:
                st.error(f"Error rendering message analytics: {str(e)}")

    def _render_user_statistics(self, start_datetime, end_datetime, days_back):
        with st.container(border=True):
            try:
                if days_back > 0:
                    status_counts = self.backend.get_user_status_counts_within_timeframe_by_platform(start_datetime, end_datetime, "instagram")
                else:
                    status_counts = self.backend.get_user_status_counts_by_platform("instagram")

                filtered_counts = {k: v for k, v in (status_counts or {}).items() if k.upper() != 'SCRAPED'}
                if not filtered_counts:
                    st.info("No user status data available for the selected time period.")
                    return

                num_statuses = len(filtered_counts)
                if num_statuses > 0:
                    cols = st.columns(num_statuses)
                    for i, (status, count) in enumerate(filtered_counts.items()):
                        display_status = status.replace("_", " ").title()
                        cols[i].metric(label=display_status, value=count)
                st.write("---")

                status_df = pd.DataFrame(filtered_counts.items(), columns=['Status', 'Count'])
                fig = px.pie(status_df, values='Count', names='Status', title="User Status Distribution", color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, width='stretch')

            except Exception as e:
                st.error(f"Error rendering user statistics: {str(e)}")

    def _render_controller_panel(self):
        """Render Instagram platform controller panel"""
        st.subheader(f"{self.const.ICONS.get('instagram', '')} Instagram Controller")
        
        try:
            from ...services.dashboards.ui import validate_client_access
            validate_client_access(self.backend.client_username)
            
            # Get platform configuration
            platform_config = Client.get_client_platforms_config(self.backend.client_username)
            instagram_config = platform_config.get('instagram', {})
            
            # Platform enable toggle
            platform_enabled = instagram_config.get('enabled', False)
            new_platform_enabled = st.toggle(
                "Enable Instagram Platform", 
                value=platform_enabled, 
                key="instagram_platform_enable"
            )
            
            if new_platform_enabled != platform_enabled:
                if Client.update_platform_enabled_status(self.backend.client_username, 'instagram', new_platform_enabled):
                    st.success(f"Instagram platform {'enabled' if new_platform_enabled else 'disabled'} successfully")
                    st.rerun()
                else:
                    st.error("Failed to update Instagram platform status")
            
            # Module toggles (only show if platform is enabled)
            if new_platform_enabled:
                st.write("### Module Controls")
                modules = instagram_config.get('modules', {})
                
                # Create columns for module toggles
                col1, col2 = st.columns(2)
                
                with col1:
                    # Fixed Response toggle
                    fixed_response_enabled = modules.get('fixed_response', {}).get('enabled', False)
                    new_fixed_response = st.toggle(
                        "Fixed Response", 
                        value=fixed_response_enabled, 
                        key="instagram_fixed_response"
                    )
                    
                    if new_fixed_response != fixed_response_enabled:
                        if Client.update_module_status(self.backend.client_username, 'instagram', 'fixed_response', new_fixed_response):
                            st.success(f"Fixed Response {'enabled' if new_fixed_response else 'disabled'}")
                            st.rerun()
                        else:
                            st.error("Failed to update Fixed Response")
                    
                    # Comment Assist toggle
                    comment_assist_enabled = modules.get('comment_assist', {}).get('enabled', False)
                    new_comment_assist = st.toggle(
                        "Comment Assist", 
                        value=comment_assist_enabled, 
                        key="instagram_comment_assist"
                    )
                    
                    if new_comment_assist != comment_assist_enabled:
                        if Client.update_module_status(self.backend.client_username, 'instagram', 'comment_assist', new_comment_assist):
                            st.success(f"Comment Assist {'enabled' if new_comment_assist else 'disabled'}")
                            st.rerun()
                        else:
                            st.error("Failed to update Comment Assist")
                
                with col2:
                    # DM Assist toggle
                    dm_assist_enabled = modules.get('dm_assist', {}).get('enabled', False)
                    new_dm_assist = st.toggle(
                        "DM Assist", 
                        value=dm_assist_enabled, 
                        key="instagram_dm_assist"
                    )
                    
                    if new_dm_assist != dm_assist_enabled:
                        if Client.update_module_status(self.backend.client_username, 'instagram', 'dm_assist', new_dm_assist):
                            st.success(f"DM Assist {'enabled' if new_dm_assist else 'disabled'}")
                            st.rerun()
                        else:
                            st.error("Failed to update DM Assist")
                    
                    # Vision toggle
                    vision_enabled = modules.get('vision', {}).get('enabled', False)
                    new_vision = st.toggle(
                        "Vision", 
                        value=vision_enabled, 
                        key="instagram_vision"
                    )
                    
                    if new_vision != vision_enabled:
                        if Client.update_module_status(self.backend.client_username, 'instagram', 'vision', new_vision):
                            st.success(f"Vision {'enabled' if new_vision else 'disabled'}")
                            st.rerun()
                        else:
                            st.error("Failed to update Vision")
            else:
                st.info("Enable the Instagram platform to access module controls.")
                
        except ValueError as e:
            st.error(f"Access denied: {str(e)}")
        except Exception as e:
            st.error(f"Error rendering controller panel: {str(e)}")

    def _render_posts_tab(self): #
        """Renders the section for managing and viewing Instagram posts with optimized performance.""" #

        # Check if we have a selected post and show the detail view directly
        if 'selected_post_id' in st.session_state and st.session_state['selected_post_id']:
            self._render_post_detail(st.session_state['selected_post_id'])
            return

        # Only show action buttons in the grid view
        col1, col2, col3, col4, col5 = st.columns(5) #

        with col1: #
            if st.button(f"{self.const.ICONS['update']} Update Posts", help="Fetch and update Instagram posts", width='stretch'): #
                with st.spinner("Fetching posts..."): #
                    try: #
                        success = self.backend.fetch_instagram_posts() #
                        if success: #
                            st.success(f"{self.const.ICONS['success']} Posts updated!") #
                            st.rerun() #
                        else: #
                            st.error(f"{self.const.ICONS['error']} Fetch failed") #
                    except Exception as e: #
                        st.error(f"Error: {str(e)}") #

        with col2: #
            if st.button(f"{self.const.ICONS['model']} AI Label", help="Auto-label posts with AI", width='stretch'): #
                with st.spinner("AI labeling..."): #
                    try: #
                        if hasattr(self.backend, 'set_post_labels_by_model'): #
                            result = self.backend.set_post_labels_by_model() #
                            if result and result.get('success'): #
                                st.success(f"Labels updated!") #
                                st.rerun() #
                            else: #
                                st.error(f"Labeling failed") #
                        else: #
                            st.error(f"Function not found") #
                    except Exception as e: #
                        st.error(f"Error: {str(e)}") #

        with col3:
            if st.button(f"{self.const.ICONS['folder']} Download", help="Download post labels as JSON", width='stretch'):
                try:
                    # Get labeled posts data from backend
                    labeled_data = self.backend.download_post_labels()

                    # Check if we got valid data
                    if isinstance(labeled_data, dict) and not labeled_data.get("error"):
                        # Convert dict to JSON string with ensure_ascii=False to properly handle Farsi/Persian characters
                        import json
                        json_data = json.dumps(labeled_data, indent=2, ensure_ascii=False)

                        # Create download link
                        import base64
                        json_bytes = json_data.encode('utf-8')
                        b64 = base64.b64encode(json_bytes).decode()
                        href = f'<a href="data:application/json;charset=utf-8;base64,{b64}" download="post_labels.json">Download JSON file</a>'

                        # Display download link
                        st.markdown(href, unsafe_allow_html=True)
                        st.success("JSON file ready for download!")
                    else:
                        st.error("Failed to prepare data for download")
                except Exception as e:
                    st.error(f"Error preparing download: {str(e)}")

        with col4:
            if st.button(f"{self.const.ICONS['delete']} Remove Labels", help="Remove all labels from posts", width='stretch'):
                try:
                    with st.spinner("Removing all labels..."):
                        updated_count = self.backend.unset_all_post_labels()
                        if updated_count > 0:
                            st.success(f"Successfully removed labels from {updated_count} posts!")
                            st.rerun()
                        else:
                            st.info("No labels were removed.")
                except Exception as e:
                    st.error(f"Error removing labels: {str(e)}")

        with col5:
            try:
                posts = self.backend.get_posts()
                all_labels = sorted(list(set(post.get('label', '') for post in posts if post.get('label', ''))))
                filter_options = ["All"] + all_labels

                selected_filter = st.selectbox(
                    f"{self.const.ICONS['label']} Filter",
                    options=filter_options,
                    index=filter_options.index(st.session_state['post_filter']) if st.session_state['post_filter'] in filter_options else 0,
                    key="post_filter_selector",
                    label_visibility="collapsed"
                )

                # Apply filter change immediately instead of using on_change
                if selected_filter != st.session_state['post_filter']:
                    st.session_state['post_filter'] = selected_filter
                    st.session_state['post_page'] = 0  # Reset to first page when filter changes
                    st.rerun()
            except Exception as e:
                st.error(f"Error loading labels: {str(e)}")

        try:
            posts = self.backend.get_posts()
            total_posts = len(posts)

            if not posts:
                st.info("No posts found. Click 'Update Posts' to fetch them.")
                return

            # Fix posts per page at 12 (remove selector)
            st.session_state['posts_per_page'] = 12

            if st.session_state['post_filter'] != "All":
                filtered_posts = [post for post in posts if post.get('label', '') == st.session_state['post_filter']]
            else:
                filtered_posts = posts

            filtered_count = len(filtered_posts)
            max_pages = (filtered_count - 1) // st.session_state['posts_per_page'] + 1 if filtered_count > 0 else 1

            if st.session_state['post_page'] >= max_pages:
                st.session_state['post_page'] = max_pages - 1

            start_idx = st.session_state['post_page'] * st.session_state['posts_per_page']
            end_idx = min(start_idx + st.session_state['posts_per_page'], filtered_count)
            current_page_posts = filtered_posts[start_idx:end_idx]

            self._render_post_grid(current_page_posts)

            if filtered_count > 0:
                # Add CSS for minimal pagination
                st.markdown("""
                <style>
                .minimal-pagination {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 5px;
                    margin: 15px 0;
                }
                .page-btn {
                    min-width: 30px !important;
                    height: 30px !important;
                    padding: 0 !important;
                    font-size: 12px !important;
                    display: inline-flex !important;
                    align-items: center;
                    justify-content: center;
                    border-radius: 4px !important;
                }
                .page-nav-btn {
                    min-width: 35px !important;
                    height: 30px !important;
                    padding: 0 8px !important;
                    font-size: 12px !important;
                }
                </style>
                """, unsafe_allow_html=True)

                # Display pagination in a single row with minimal styling
                st.markdown('<div class="minimal-pagination">', unsafe_allow_html=True)
                cols = st.columns([1, 6, 1])

                with cols[0]:
                    prev_disabled = st.session_state['post_page'] <= 0
                    if st.button(f"{self.const.ICONS['previous']}",
                                disabled=prev_disabled,
                                key="prev_page_btn",
                                help="Previous page",
                                width='stretch'):
                        st.session_state['post_page'] -= 1
                        st.rerun()

                with cols[1]:
                    # Create a multi-column layout for page numbers
                    if max_pages <= 10:
                        # If few pages, show all page numbers
                        page_cols = st.columns(max_pages)
                        for i in range(max_pages):
                            with page_cols[i]:
                                current = i == st.session_state['post_page']
                                if st.button(f"{i+1}",
                                           key=f"page_btn_{i}",
                                           disabled=current,
                                           type="primary" if current else "secondary"):
                                    st.session_state['post_page'] = i
                                    st.rerun()
                    else:
                        # For more pages, use a smart pagination layout
                        # Always show: first page, current page, last page, and pages around current
                        current_page = st.session_state['post_page']
                        pages_to_show = {0, current_page, max_pages - 1}  # First, current, last

                    # Add pages around current page
                        for i in range(max(0, current_page - 2), min(max_pages, current_page + 3)):
                            pages_to_show.add(i)

                    # Convert to sorted list
                        pages_to_show = sorted(list(pages_to_show))

                        # Calculate where to add "..."
                        gaps = []
                        for i in range(len(pages_to_show) - 1):
                            if pages_to_show[i+1] - pages_to_show[i] > 1:
                                gaps.append(i)

                        # Add the gaps to the display sequence
                        display_sequence = []
                        for i, page in enumerate(pages_to_show):
                            display_sequence.append(page)
                            if i in gaps:
                                display_sequence.append("...")

                        # Create columns for each page number or ellipsis
                        page_cols = st.columns(len(display_sequence))

                        for i, item in enumerate(display_sequence):
                            with page_cols[i]:
                                if item == "...":
                                    st.markdown("...")
                                else:
                                    current = item == current_page
                                    if st.button(f"{item+1}",
                                              key=f"page_btn_{item}",
                                              disabled=current,
                                              type="primary" if current else "secondary"):
                                        st.session_state['post_page'] = item
                                        st.rerun()

                with cols[2]:
                    next_disabled = st.session_state['post_page'] >= max_pages - 1
                    if st.button(f"{self.const.ICONS['next']}",
                                disabled=next_disabled,
                                key="next_page_btn",
                                help="Next page",
                                width='stretch'):
                        st.session_state['post_page'] += 1
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

                # Display post count information as a small caption
                st.caption(f"Showing {start_idx+1}-{end_idx} of {filtered_count} posts")

        except Exception as e: #
            st.error(f"Error loading post grid: {str(e)}") #

    def _render_stories_tab(self):
        """Renders the stories tab with consistent grid layout and functionality as posts"""
        # Check if we have a selected story and show detail view
        if st.session_state['selected_story_id']:
            self._render_story_detail(st.session_state['selected_story_id'])
            return

        # Action buttons row (same structure as posts)
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            if st.button(f"{self.const.ICONS['update']} Update Stories",
                        help="Fetch and update Instagram stories",
                        width='stretch'):
                with st.spinner("Fetching stories..."):
                    try:
                        success = self.backend.fetch_instagram_stories()
                        if success:
                            st.success(f"{self.const.ICONS['success']} Stories updated!")
                            st.rerun()
                        else:
                            st.error(f"{self.const.ICONS['error']} Fetch failed")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        with col2:
            if st.button(f"{self.const.ICONS['model']} AI Label",
                        help="Auto-label stories with AI",
                        width='stretch'):
                with st.spinner("AI labeling..."):
                    try:
                        result = self.backend.set_story_labels_by_model()
                        if result and result.get('success'):
                            st.success(f"Labels updated!")
                            st.rerun()
                        else:
                            st.error(f"Labeling failed")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        with col3:
            if st.button(f"{self.const.ICONS['folder']} Download",
                        help="Download story labels as JSON",
                        width='stretch'):
                try:
                    labeled_data = self.backend.download_story_labels()
                    if isinstance(labeled_data, dict) and not labeled_data.get("error"):
                        import json
                        json_data = json.dumps(labeled_data, indent=2, ensure_ascii=False)
                        import base64
                        json_bytes = json_data.encode('utf-8')
                        b64 = base64.b64encode(json_bytes).decode()
                        href = f'<a href="data:application/json;charset=utf-8;base64,{b64}" download="story_labels.json">Download JSON file</a>'
                        st.markdown(href, unsafe_allow_html=True)
                        st.success("JSON file ready for download!")
                    else:
                        st.error("Failed to prepare data for download")
                except Exception as e:
                    st.error(f"Error preparing download: {str(e)}")

        with col4:
            if st.button(f"{self.const.ICONS['delete']} Remove Labels",
                        help="Remove all labels from stories",
                        width='stretch'):
                try:
                    with st.spinner("Removing all labels..."):
                        updated_count = self.backend.unset_all_story_labels()
                        if updated_count > 0:
                            st.success(f"Successfully removed labels from {updated_count} stories!")
                            st.rerun()
                        else:
                            st.info("No labels were removed.")
                except Exception as e:
                    st.error(f"Error removing labels: {str(e)}")

        with col5:
            try:
                stories = self.backend.get_stories()
                all_labels = sorted(list(set(story.get('label', '') for story in stories if story.get('label', ''))))
                filter_options = ["All"] + all_labels

                selected_filter = st.selectbox(
                    f"{self.const.ICONS['label']} Filter",
                    options=filter_options,
                    index=filter_options.index(st.session_state['story_filter']) if st.session_state['story_filter'] in filter_options else 0,
                    key="story_filter_selector",
                    label_visibility="collapsed"
                )

                if selected_filter != st.session_state['story_filter']:
                    st.session_state['story_filter'] = selected_filter
                    st.session_state['story_page'] = 0
                    st.rerun()
            except Exception as e:
                st.error(f"Error loading labels: {str(e)}")

        try:
            stories = self.backend.get_stories()
            total_stories = len(stories)

            if not stories:
                st.info("No stories found. Click 'Update Stories' to fetch them.")
                return

            st.session_state['stories_per_page'] = 12

            if st.session_state['story_filter'] != "All":
                filtered_stories = [story for story in stories if story.get('label', '') == st.session_state['story_filter']]
            else:
                filtered_stories = stories

            filtered_count = len(filtered_stories)
            max_pages = (filtered_count - 1) // st.session_state['stories_per_page'] + 1 if filtered_count > 0 else 1

            if st.session_state['story_page'] >= max_pages:
                st.session_state['story_page'] = max_pages - 1

            start_idx = st.session_state['story_page'] * st.session_state['stories_per_page']
            end_idx = min(start_idx + st.session_state['stories_per_page'], filtered_count)
            current_page_stories = filtered_stories[start_idx:end_idx]

            self._render_story_grid(current_page_stories)

            if filtered_count > 0:
                # Pagination controls (same as posts)
                st.markdown("""
                <style>
                .minimal-pagination {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 5px;
                    margin: 15px 0;
                }
                .page-btn {
                    min-width: 30px !important;
                    height: 30px !important;
                    padding: 0 !important;
                    font-size: 12px !important;
                    display: inline-flex !important;
                    align-items: center;
                    justify-content: center;
                    border-radius: 4px !important;
                }
                .page-nav-btn {
                    min-width: 35px !important;
                    height: 30px !important;
                    padding: 0 8px !important;
                    font-size: 12px !important;
                }
                </style>
                """, unsafe_allow_html=True)

                st.markdown('<div class="minimal-pagination">', unsafe_allow_html=True)
                cols = st.columns([1, 6, 1])

                with cols[0]:
                    prev_disabled = st.session_state['story_page'] <= 0
                    if st.button(f"{self.const.ICONS['previous']}",
                                disabled=prev_disabled,
                                key="prev_story_page_btn",
                                help="Previous page",
                                width='stretch'):
                        st.session_state['story_page'] -= 1
                        st.rerun()

                with cols[1]:
                    if filtered_count <= 10:
                        page_cols = st.columns(filtered_count)
                        for i in range(filtered_count):
                            with page_cols[i]:
                                current = i == st.session_state['story_page']
                                if st.button(f"{i+1}",
                                           key=f"story_page_btn_{i}",
                                           disabled=current,
                                           type="primary" if current else "secondary"):
                                    st.session_state['story_page'] = i
                                    st.rerun()
                    else:
                        current_page = st.session_state['story_page']
                        pages_to_show = {0, current_page, filtered_count - 1}
                        for i in range(max(0, current_page - 2), min(filtered_count, current_page + 3)):
                            pages_to_show.add(i)
                        pages_to_show = sorted(list(pages_to_show))

                        gaps = []
                        for i in range(len(pages_to_show) - 1):
                            if pages_to_show[i+1] - pages_to_show[i] > 1:
                                gaps.append(i)

                        display_sequence = []
                        for i, page in enumerate(pages_to_show):
                            display_sequence.append(page)
                            if i in gaps:
                                display_sequence.append("...")

                        page_cols = st.columns(len(display_sequence))

                        for i, item in enumerate(display_sequence):
                            with page_cols[i]:
                                if item == "...":
                                    st.markdown("...")
                                else:
                                    current = item == current_page
                                    if st.button(f"{item+1}",
                                              key=f"story_page_btn_{item}",
                                              disabled=current,
                                              type="primary" if current else "secondary"):
                                        st.session_state['story_page'] = item
                                        st.rerun()

                with cols[2]:
                    next_disabled = st.session_state['story_page'] >= max_pages - 1
                    if st.button(f"{self.const.ICONS['next']}",
                                disabled=next_disabled,
                                key="next_story_page_btn",
                                help="Next page",
                                width='stretch'):
                        st.session_state['story_page'] += 1
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

                st.caption(f"Showing {start_idx+1}-{end_idx} of {filtered_count} stories")

        except Exception as e:
            st.error(f"Error loading story grid: {str(e)}")

    def _render_story_grid(self, stories_to_display):
        """Renders a paginated grid of Instagram stories matching post grid style"""
        if 'selected_story_id' not in st.session_state:
            st.session_state['selected_story_id'] = None

        num_columns = 4
        cols = st.columns(num_columns)

        # Custom CSS for the grid (same as posts)
        st.markdown("""
        <style>
        .story-grid {
            margin-bottom: 20px;
        }
        .story-image-container {
            position: relative;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .story-image-container:hover {
            transform: translateY(-5px);
        }
        .story-image-container img {
            width: 100%;
            aspect-ratio: 1;
            object-fit: cover;
            display: block;
        }
        .story-label {
            position: absolute;
            bottom: 10px;
            left: 10px;
            background-color: rgba(0,0,0,0.7);
            color: white;
            font-size: 11px;
            padding: 4px 8px;
            border-radius: 12px;
            max-width: 80%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .story-view-btn {
            width: 100% !important;
            margin-top: 0 !important;
            padding: 4px 0 !important;
            font-size: 13px !important;
            border-radius: 6px !important;
            background-color: #0095f6 !important;
            color: white !important;
            border: none !important;
            font-weight: 500 !important;
            cursor: pointer;
        }
        </style>
        """, unsafe_allow_html=True)

        for index, story in enumerate(stories_to_display):
            story_id = story.get('id')
            if not story_id:
                story_id_key = f"index_{index}"
            else:
                story_id_key = str(story_id)

            col_index = index % num_columns
            with cols[col_index]:
                with st.container():
                    media_url = story.get('media_url')
                    thumbnail_url = story.get('thumbnail_url')
                    label = story.get('label', '')

                    st.markdown(f"""
                    <div class="story-image-container">
                        <img src="{thumbnail_url or media_url}" alt="Instagram story">
                        {f'<div class="story-label">{label}</div>' if label else ''}
                    </div>
                    """, unsafe_allow_html=True)

                    view_btn = st.button("View Details", key=f"view_story_btn_{story_id_key}", width='stretch')

                    if view_btn:
                        st.session_state['selected_story_id'] = story_id
                        st.rerun()

    def _render_story_detail(self, story_id):
        """Renders the detail view for a single Instagram story matching post detail style"""
        try:
            stories = self.backend.get_stories()

            # Get all stories with the same label if filtered view is active
            if st.session_state['story_filter'] != "All":
                filtered_stories = [story for story in stories if story.get('label', '') == st.session_state['story_filter']]
            else:
                filtered_stories = stories

            # Find the current story
            story = next((s for s in filtered_stories if s.get('id') == story_id), None)

            # Get the index of the current story in the filtered list
            if story:
                current_index = filtered_stories.index(story)
                total_stories = len(filtered_stories)
                prev_index = (current_index - 1) % total_stories if total_stories > 1 else None
                next_index = (current_index + 1) % total_stories if total_stories > 1 else None

                prev_story_id = filtered_stories[prev_index]['id'] if prev_index is not None else None
                next_story_id = filtered_stories[next_index]['id'] if next_index is not None else None
            else:
                current_index = None
                total_stories = len(filtered_stories)
                prev_story_id = None
                next_story_id = None

            if not story:
                st.error(f"Story not found with ID: {story_id}")
                if st.button("Back to grid", width='stretch'):
                    st.session_state['selected_story_id'] = None
                    st.rerun()
                return

            # Apply styling for the details page (same as posts)
            st.markdown("""
            <style>
            .story-detail-image {
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            .story-detail-section {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 16px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            }
            .story-caption {
                max-height: 200px;
                overflow-y: auto;
                padding: 10px;
                background-color: white;
                border-radius: 6px;
                border: 1px solid #eee;
                margin-top: 5px;
            }
            .story-fixed-response-field {
                background-color: white;
                border-radius: 6px;
                border: 1px solid #eee;
                padding: 10px;
                margin-top: 5px;
            }
            .story-detail-navigation {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 15px;
            }
            .story-pagination-counter {
                text-align: center;
                font-size: 14px;
                color: #666;
            }
            .story-mini-header {
                font-size: 16px;
                font-weight: 600;
                margin-bottom: 8px;
            }
            </style>
            """, unsafe_allow_html=True)

            # Navigation header with back, prev, next buttons
            cols = st.columns([1, 3, 1])

            with cols[0]:
                if st.button("Back", key="back_to_story_grid_btn", help="Back to grid", width='stretch'):
                    st.session_state['selected_story_id'] = None
                    st.rerun()

            with cols[2]:
                nav_cols = st.columns(2)
                with nav_cols[0]:
                    prev_disabled = prev_story_id is None
                    if st.button(f"{self.const.ICONS['previous']}",
                               key="detail_prev_story_btn",
                               disabled=prev_disabled,
                               help="Previous story",
                               width='stretch'):
                        if prev_story_id:
                            st.session_state['selected_story_id'] = prev_story_id
                            st.rerun()

                with nav_cols[1]:
                    next_disabled = next_story_id is None
                    if st.button(f"{self.const.ICONS['next']}",
                               key="detail_next_story_btn",
                               disabled=next_disabled,
                               help="Next story",
                               width='stretch'):
                        if next_story_id:
                            st.session_state['selected_story_id'] = next_story_id
                            st.rerun()

                if current_index is not None:
                    st.markdown(
                        f'<div style="text-align: center; font-size: 0.9em; color: #666; margin-top: 10px;">'
                        f'Story <span style="font-size: 1.2em; font-weight: bold;">{current_index + 1}</span> of {total_stories}'
                        f'</div>',
                        unsafe_allow_html=True
                    )

            # Layout for story details
            col1, col2 = st.columns([2, 3])

            with col1:
                # Media display
                st.markdown('<div class="story-detail-image">', unsafe_allow_html=True)
                media_url = story.get('media_url')
                thumbnail_url = story.get('thumbnail_url')
                media_type = story.get('media_type', '').lower()

                if media_type == "video":
                    try:
                        st.video(media_url)
                    except Exception as e:
                        st.error(f"Unable to play video: {str(e)}")
                        if thumbnail_url:
                            st.image(thumbnail_url, width='stretch')
                            st.caption("Video thumbnail (video playback unavailable)")
                        else:
                            st.warning("Video playback unavailable")
                elif media_url:
                    st.image(media_url, width='stretch')
                else:
                    st.warning("No media available")

                st.markdown('</div>', unsafe_allow_html=True)

                # Label selector section
                with st.container():
                    try:
                        products_data = self.backend.get_products()
                        product_titles = sorted([p['title'] for p in products_data if p.get('title')])
                        custom_labels = st.session_state.get('custom_labels', [])
                        all_labels = ["-- Select --"] + sorted(list(set(product_titles + custom_labels)))

                        current_label = story.get('label', '')
                        try:
                            default_select_index = all_labels.index(current_label) if current_label else 0
                        except ValueError:
                            if current_label:
                                all_labels.append(current_label)
                                default_select_index = all_labels.index(current_label)
                            else:
                                default_select_index = 0

                        label_col, ai_col, remove_col = st.columns([3, 1, 1])

                        with label_col:
                            select_key = f"story_label_select_detail_{story_id}"
                            selected_label = st.selectbox(
                                "Select Label",
                                options=all_labels,
                                key=select_key,
                                index=default_select_index
                            )

                        with ai_col:
                            st.write("")
                            if st.button(f"{self.const.ICONS['brain']}", key=f"story_auto_label_btn_{story_id}", help="Auto-label using AI"):
                                with st.spinner("Analyzing image..."):
                                    result = self.backend.set_single_story_label_by_model(story_id)
                                    if result and result.get("success"):
                                        st.success(f"Image labeled as: {result.get('label')}")
                                        st.rerun()
                                    else:
                                        error_msg = result.get('message', 'Unknown error') if result else 'Unknown error'
                                        st.error(f"Failed to label image: {error_msg}")
                                        if "Model confidence too low" in error_msg:
                                            st.info("The AI model wasn't confident enough to determine a label for this image.")

                        with remove_col:
                            st.write("")
                            if st.button(f"{self.const.ICONS['delete']}", key=f"story_remove_label_btn_{story_id}", help="Remove label"):
                                if self.backend.remove_story_label(story_id):
                                    st.success("Label removed successfully")
                                    st.rerun()
                                else:
                                    st.error("Failed to remove label")

                        if selected_label != current_label and selected_label != "-- Select --":
                            try:
                                label_success = self.backend.set_story_label(story_id, selected_label)
                                if label_success:
                                    st.success(f"{self.const.ICONS['success']} Label updated")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"{self.const.ICONS['error']} Error saving label: {str(e)}")
                    except Exception as e:
                        st.error(f"Error loading labels: {str(e)}")

                    label_input_col, label_btn_col = st.columns([3, 1])
                    with label_input_col:
                        new_label = st.text_input(
                            "Add custom label",
                            key=f"story_detail_new_custom_label_{story_id}",
                            placeholder="Add custom label",
                            label_visibility="collapsed"
                        )

                    with label_btn_col:
                        if st.button(f"{self.const.ICONS['add']}", key=f"story_detail_add_label_btn_{story_id}", help="Add label", width='stretch'):
                            new_label_stripped = new_label.strip()
                            if new_label_stripped and new_label_stripped not in st.session_state['custom_labels']:
                                st.session_state['custom_labels'].append(new_label_stripped)
                                st.success(f"Added '{new_label_stripped}'")
                                st.rerun()
                            elif not new_label_stripped:
                                st.warning("Label cannot be empty")
                            else:
                                st.warning(f"Label already exists")

            with col2:
                # Story details - Caption
                st.write("")
                st.markdown('<div class="story-mini-header">Caption</div>', unsafe_allow_html=True)
                caption = story.get('caption', 'No caption available')

                st.markdown(f'<div style="margin-bottom:20px;">{caption}</div>', unsafe_allow_html=True)

                # Admin Explanation section
                st.write("")

                try:
                    current_explanation = self.backend.get_story_admin_explanation(story_id)

                    with st.form(key=f"story_admin_explanation_form_{story_id}", border=False):
                        explanation = st.text_area(
                            "Explain",
                            value=current_explanation if current_explanation else "",
                            placeholder="Add an explanation for this story",
                            key=f"story_admin_explanation_{story_id}"
                        )

                        exp_col1, exp_col2 = st.columns(2)

                        with exp_col1:
                            save_exp_button = st.form_submit_button(
                                f"{self.const.ICONS['save']} Save Explanation",
                                width='stretch'
                            )

                        with exp_col2:
                            remove_exp_button = st.form_submit_button(
                                f"{self.const.ICONS['delete']} Remove Explanation",
                                type="secondary",
                                width='stretch'
                            )

                        if save_exp_button:
                            if explanation.strip():
                                try:
                                    success = self.backend.set_story_admin_explanation(story_id, explanation.strip())
                                    if success:
                                        st.success(f"{self.const.ICONS['success']} Explanation saved!")
                                        st.rerun()
                                    else:
                                        st.error(f"{self.const.ICONS['error']} Failed to save explanation")
                                except Exception as e:
                                    st.error(f"{self.const.ICONS['error']} Error saving explanation: {str(e)}")
                            else:
                                st.warning("Explanation cannot be empty")

                        if remove_exp_button:
                            try:
                                success = self.backend.remove_story_admin_explanation(story_id)
                                if success:
                                    st.success("Explanation removed")
                                    st.rerun()
                                else:
                                    st.error("Failed to remove explanation")
                            except Exception as e:
                                st.error(f"Error removing explanation: {str(e)}")

                except Exception as e:
                    st.error(f"Error loading admin explanation: {str(e)}")

                # Fixed response editing functionality
                st.write("")
                st.markdown('<div class="story-mini-header">Fixed Response</div>', unsafe_allow_html=True)

                try:
                    raw_responses_data = self.backend.get_story_fixed_responses(story_id)
                except Exception as e:
                    raw_responses_data = None
                    st.error(f"Error loading fixed responses: {str(e)}")

                exist_tab, add_tab = st.tabs(["Existing", "Add New"])

                with exist_tab:
                    fixed_responses_to_display = []
                    if isinstance(raw_responses_data, list):
                        fixed_responses_to_display = raw_responses_data
                    elif isinstance(raw_responses_data, dict) and raw_responses_data:
                        fixed_responses_to_display = [raw_responses_data]

                    if not fixed_responses_to_display:
                        st.info("No fixed response exists for this story. Use the 'Add New' tab to create one.")
                    else:
                        for index, response_item in enumerate(fixed_responses_to_display):
                            if not isinstance(response_item, dict):
                                st.warning(f"Skipping an invalid fixed response item (item {index + 1}).")
                                continue

                            st.markdown("---")
                            form_key = f"story_existing_response_form_{story_id}_{index}"
                            original_trigger_keyword = response_item.get("trigger_keyword", "")

                            with st.form(key=form_key, border=True):
                                st.markdown(f"**Response for Trigger: \"{original_trigger_keyword}\"**" if original_trigger_keyword else f"**Response Item {index+1}**")

                                trigger_keyword_input = st.text_input(
                                    "Trigger keyword",
                                    value=original_trigger_keyword,
                                    key=f"trigger_{form_key}"
                                )
                                dm_response_input = st.text_area(
                                    "DM reply",
                                    value=response_item.get("direct_response_text", ""),
                                    key=f"dm_{form_key}"
                                )
                                col_update, col_delete = st.columns(2)
                                with col_update:
                                    update_button = st.form_submit_button(f"{self.const.ICONS['save']} Update This Response", width='stretch')
                                with col_delete:
                                    delete_button = st.form_submit_button(
                                        f"{self.const.ICONS['delete']} Remove This Response",
                                        type="secondary",
                                        width='stretch'
                                    )

                                if update_button:
                                    new_trigger_keyword = trigger_keyword_input.strip()
                                    if not new_trigger_keyword:
                                        st.error("Trigger keyword is required.")
                                    else:
                                        success = self.backend.create_or_update_story_fixed_response(
                                            story_id=story_id,
                                            trigger_keyword=new_trigger_keyword,
                                            direct_response_text=dm_response_input.strip() or None
                                        )
                                        if success:
                                            st.success(f"Response for '{new_trigger_keyword}' processed successfully!")
                                            if original_trigger_keyword and original_trigger_keyword != new_trigger_keyword:
                                                st.info(f"Content previously associated with '{original_trigger_keyword}' is now under '{new_trigger_keyword}'. The old trigger entry might still exist if not explicitly managed by the backend as a 'rename'.")
                                            st.rerun()
                                        else:
                                            st.error(f"Failed to process response for '{new_trigger_keyword}'.")

                                if delete_button:
                                    if not original_trigger_keyword:
                                        st.error("Cannot delete response: Original trigger keyword is missing.")
                                    else:
                                        try:
                                            success = self.backend.delete_story_fixed_response(story_id, original_trigger_keyword)
                                            if success:
                                                st.success(f"Response for '{original_trigger_keyword}' removed successfully.")
                                                st.rerun()
                                            else:
                                                st.error(f"Failed to remove response for '{original_trigger_keyword}'.")
                                        except Exception as e:
                                            st.error(f"Error removing response: {str(e)}")

                with add_tab:
                    try:
                        with st.form(key=f"story_new_response_form_{story_id}", border=False):
                            new_trigger_keyword = st.text_input(
                                "Trigger keyword",
                                placeholder="Enter words that will trigger this response"
                            )
                            new_dm_response = st.text_area(
                                "DM reply",
                                placeholder="Response sent as DM when someone messages with trigger words"
                            )
                            new_submit_button = st.form_submit_button(f"{self.const.ICONS['add']} Create", width='stretch')
                            if new_submit_button:
                                try:
                                    if new_trigger_keyword.strip():
                                        new_success = self.backend.create_or_update_story_fixed_response(
                                            story_id=story_id,
                                            trigger_keyword=new_trigger_keyword.strip(),
                                            direct_response_text=new_dm_response.strip() if new_dm_response.strip() else None
                                        )
                                        if new_success:
                                            st.success(f"{self.const.ICONS['success']} Created!")
                                            st.rerun()
                                    else:
                                        st.error("Trigger keyword is required")
                                except Exception as e:
                                    st.error(f"{self.const.ICONS['error']} Error creating: {str(e)}")
                    except Exception as e:
                        st.error(f"Error loading form: {str(e)}")

        except Exception as e:
            st.error(f"Error loading story details: {str(e)}")
            if st.button("Back to grid", width='stretch'):
                st.session_state['selected_story_id'] = None
                st.rerun()

    def _render_post_grid(self, posts_to_display): #
        """Renders a paginated grid of Instagram posts with minimal UI""" #
        if 'selected_post_id' not in st.session_state:
            st.session_state['selected_post_id'] = None

        num_columns = 4 #
        cols = st.columns(num_columns) #

        # Custom CSS for the Instagram-like grid
        st.markdown("""
        <style>
        .post-grid {
            margin-bottom: 20px;
        }
        .post-image-container {
            position: relative;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .post-image-container:hover {
            transform: translateY(-5px);
        }
        .post-image-container img {
            width: 100%;
            aspect-ratio: 1;
            object-fit: cover;
            display: block;
        }
        .post-label {
            position: absolute;
            bottom: 10px;
            left: 10px;
            background-color: rgba(0,0,0,0.7);
            color: white;
            font-size: 11px;
            padding: 4px 8px;
            border-radius: 12px;
            max-width: 80%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .view-btn {
            width: 100% !important;
            margin-top: 0 !important;
            padding: 4px 0 !important;
            font-size: 13px !important;
            border-radius: 6px !important;
            background-color: #0095f6 !important;
            color: white !important;
            border: none !important;
            font-weight: 500 !important;
            cursor: pointer;
        }
        </style>
        """, unsafe_allow_html=True)

        # Use Streamlit columns for the grid
        for index, post in enumerate(posts_to_display): #
            post_id = post.get('id') #
            if not post_id: #
                post_id_key = f"index_{index}" #
            else: #
                post_id_key = str(post_id) #

            col_index = index % num_columns #
            with cols[col_index]: #
                # Create a container for the post
                with st.container():
                    # Get media URLs and label for post
                    media_url = post.get('media_url') #
                    thumbnail_url = post.get('thumbnail_url')
                    label = post.get('label', '')

                    # Show the image in a container
                    st.markdown(f"""
                    <div class="post-image-container">
                        <img src="{thumbnail_url or media_url}" alt="Instagram post">
                        {f'<div class="post-label">{label}</div>' if label else ''}
                    </div>
                    """, unsafe_allow_html=True)

                    # Use a regular button styled to be small and flat
                    view_btn = st.button("View Details", key=f"view_btn_{post_id_key}", width='stretch')

                    # Handle click
                    if view_btn:
                        st.session_state['selected_post_id'] = post_id
                        st.rerun()

    def _render_post_detail(self, post_id):
        """Renders the detail view for a single Instagram post"""
        posts = self.backend.get_posts()

        # Get all posts with the same label if filtered view is active
        if st.session_state['post_filter'] != "All":
            filtered_posts = [post for post in posts if post.get('label', '') == st.session_state['post_filter']]
        else:
            filtered_posts = posts

        # Find the current post
        post = next((p for p in filtered_posts if p.get('id') == post_id), None)

        # Get the index of the current post in the filtered list
        if post:
            current_index = filtered_posts.index(post)
            total_posts = len(filtered_posts)
            prev_index = (current_index - 1) % total_posts if total_posts > 1 else None
            next_index = (current_index + 1) % total_posts if total_posts > 1 else None

            prev_post_id = filtered_posts[prev_index]['id'] if prev_index is not None else None
            next_post_id = filtered_posts[next_index]['id'] if next_index is not None else None
        else:
            # Post not found in current filter
            current_index = None
            total_posts = len(filtered_posts)
            prev_post_id = None
            next_post_id = None

        if not post:
            st.error(f"Post not found with ID: {post_id}")
            if st.button("Back to grid", width='stretch'):
                st.session_state['selected_post_id'] = None
                st.rerun()
            return

        # Apply some styling for the details page
        st.markdown("""
        <style>
        .post-detail-image {
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .post-detail-section {
            background-color: #f8f9fa;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        }
        .post-caption {
            max-height: 200px;
            overflow-y: auto;
            padding: 10px;
            background-color: white;
            border-radius: 6px;
            border: 1px solid #eee;
            margin-top: 5px;
        }
        .fixed-response-field {
            background-color: white;
            border-radius: 6px;
            border: 1px solid #eee;
            padding: 10px;
            margin-top: 5px;
        }
        .detail-navigation {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }
        .pagination-counter {
            text-align: center;
            font-size: 14px;
            color: #666;
        }
        .mini-header {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        </style>
        """, unsafe_allow_html=True)

        # Simplified navigation header with only back, prev, next buttons
        cols = st.columns([1, 3, 1])

        with cols[0]:
            # Back button
            if st.button("Back", key="back_to_grid_btn", help="Back to grid", width='stretch'):
                st.session_state['selected_post_id'] = None
                st.rerun()

        with cols[2]:
            # Navigation buttons container
            nav_cols = st.columns(2)
            with nav_cols[0]:
                # Previous button
                prev_disabled = prev_post_id is None
                if st.button(f"{self.const.ICONS['previous']}",
                           key="detail_prev_post_btn",
                           disabled=prev_disabled,
                           help="Previous post",
                           width='stretch'):
                    if prev_post_id:
                        st.session_state['selected_post_id'] = prev_post_id
                        st.rerun()

            with nav_cols[1]:
                # Next button
                next_disabled = next_post_id is None
                if st.button(f"{self.const.ICONS['next']}",
                           key="detail_next_post_btn",
                           disabled=next_disabled,
                           help="Next post",
                           width='stretch'):
                    if next_post_id:
                        st.session_state['selected_post_id'] = next_post_id
                        st.rerun()

            # Add post counter below navigation buttons
            if current_index is not None:
                st.markdown(
                    f'<div style="text-align: center; font-size: 0.9em; color: #666; margin-top: 10px;">'
                    f'Post <span style="font-size: 1.2em; font-weight: bold;">{current_index + 1}</span> of {total_posts}'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # Layout for post details
        col1, col2 = st.columns([2, 3])

        with col1:
            # Image display with custom class
            st.markdown('<div class="post-detail-image">', unsafe_allow_html=True)
            media_url = post.get('media_url')
            thumbnail_url = post.get('thumbnail_url')
            media_type = post.get('media_type', '').lower()

            if media_type == "video":
                try:
                    # For videos, use the native video player
                    st.video(media_url)
                except Exception as e:
                    # If video player fails, show error and fallback
                    st.error(f"Unable to play video: {str(e)}")
                    if thumbnail_url:
                        st.image(thumbnail_url, width='stretch')
                        st.caption("Video thumbnail (video playback unavailable)")
                    else:
                        st.warning("Video playback unavailable")
            elif media_url:
                # For images, display the image
                st.image(media_url, width='stretch')
            else:
                st.warning("No media available")

            st.markdown('</div>', unsafe_allow_html=True)

            # Add custom label input section below the image
            with st.container():
                # Get product titles for dropdown (moved from settings section)
                try:
                    products_data = self.backend.get_products()
                    product_titles = sorted([p['title'] for p in products_data if p.get('title')])
                    custom_labels = st.session_state.get('custom_labels', [])
                    all_labels = ["-- Select --"] + sorted(list(set(product_titles + custom_labels)))

                    current_label = post.get('label', '')
                    try:
                        default_select_index = all_labels.index(current_label) if current_label else 0
                    except ValueError:
                        if current_label:
                            all_labels.append(current_label)
                            default_select_index = all_labels.index(current_label)
                        else:
                            default_select_index = 0

                    # Add columns for label selection and buttons
                    label_col, ai_col, remove_col = st.columns([3, 1, 1])

                    with label_col:
                        # Label selector
                        select_key = f"label_select_detail_{post_id}"
                        selected_label = st.selectbox(
                            "Select Label",  # Added label parameter
                            options=all_labels,
                            key=select_key,
                            index=default_select_index
                        )

                    with ai_col:
                        # Auto-label button
                        st.write("") # Add space to align with selectbox
                        if st.button(f"{self.const.ICONS['brain']}", key=f"auto_label_btn_{post_id}", help="Auto-label using AI"):
                            with st.spinner("Analyzing image..."):
                                # Call backend method to set label using vision model
                                result = self.backend.set_single_post_label_by_model(post_id)
                                if result and result.get("success"):
                                    st.success(f"Image labeled as: {result.get('label')}")
                                    st.rerun()
                                else:
                                    error_msg = result.get('message', 'Unknown error') if result else 'Unknown error'
                                    st.error(f"Failed to label image: {error_msg}")
                                    # If the error is about model confidence, show a more user-friendly message
                                    if "Model confidence too low" in error_msg:
                                        st.info("The AI model wasn't confident enough to determine a label for this image.")

                    with remove_col:
                        # Remove label button
                        st.write("") # Add space to align with selectbox
                        if st.button(f"{self.const.ICONS['delete']}", key=f"remove_label_btn_{post_id}", help="Remove label"):
                            if self.backend.remove_post_label(post_id):
                                st.success("Label removed successfully")
                                st.rerun()
                            else:
                                st.error("Failed to remove label")

                    # Handle label update when selection changes
                    if selected_label != current_label and selected_label != "-- Select --":
                        try:
                            label_success = self.backend.set_post_label(post_id, selected_label)
                            if label_success:
                                st.success(f"{self.const.ICONS['success']} Label updated")
                                st.rerun()
                        except Exception as e:
                            st.error(f"{self.const.ICONS['error']} Error saving label: {str(e)}")
                except Exception as e:
                    st.error(f"Error loading labels: {str(e)}")

                # Custom label input field
                label_input_col, label_btn_col = st.columns([3, 1])
                with label_input_col:
                    new_label = st.text_input(
                        "Add custom label",
                        key=f"detail_new_custom_label_{post_id}",
                        placeholder="Add custom label",
                        label_visibility="collapsed"
                    )

                with label_btn_col:
                    if st.button(f"{self.const.ICONS['add']}", key=f"detail_add_label_btn_{post_id}", help="Add label", width='stretch'):
                        new_label_stripped = new_label.strip()
                        if new_label_stripped and new_label_stripped not in st.session_state['custom_labels']:
                            st.session_state['custom_labels'].append(new_label_stripped)
                            st.success(f"Added '{new_label_stripped}'")
                            st.rerun()
                        elif not new_label_stripped:
                            st.warning("Label cannot be empty")
                        else:
                            st.warning(f"Label already exists")

        with col2:
            # Post details - Caption
            st.write("")  # Add some spacing
            st.markdown('<div class="mini-header">Caption</div>', unsafe_allow_html=True)
            caption = post.get('caption', 'No caption available')

            st.markdown(f'<div style="margin-bottom:20px;">{caption}</div>', unsafe_allow_html=True)

            # Admin Explanation section
            st.write("")  # Add some spacing

            # Get existing admin explanation
            try:
                current_explanation = self.backend.get_post_admin_explanation(post_id)

                # Create a form for the admin explanation
                with st.form(key=f"admin_explanation_form_{post_id}", border=False):
                    # Text area for explanation
                    explanation = st.text_area(
                        "Explain",
                        value=current_explanation if current_explanation else "",
                        placeholder="Add an explanation for this post",
                        key=f"admin_explanation_{post_id}"
                    )

                    # Buttons row
                    exp_col1, exp_col2 = st.columns(2)

                    with exp_col1:
                        # Save button
                        save_exp_button = st.form_submit_button(
                            f"{self.const.ICONS['save']} Save Explanation",
                            width='stretch'
                        )

                    with exp_col2:
                        # Remove button
                        remove_exp_button = st.form_submit_button(
                            f"{self.const.ICONS['delete']} Remove Explanation",
                            type="secondary",
                            width='stretch'
                        )

                    if save_exp_button:
                        if explanation.strip():
                            try:
                                success = self.backend.set_post_admin_explanation(post_id, explanation.strip())
                                if success:
                                    st.success(f"{self.const.ICONS['success']} Explanation saved!")
                                    st.rerun()
                                else:
                                    st.error(f"{self.const.ICONS['error']} Failed to save explanation")
                            except Exception as e:
                                st.error(f"{self.const.ICONS['error']} Error saving explanation: {str(e)}")
                        else:
                            st.warning("Explanation cannot be empty")

                    if remove_exp_button:
                        try:
                            success = self.backend.remove_post_admin_explanation(post_id)
                            if success:
                                st.success("Explanation removed")
                                st.rerun()
                            else:
                                st.error("Failed to remove explanation")
                        except Exception as e:
                            st.error(f"Error removing explanation: {str(e)}")

            except Exception as e:
                st.error(f"Error loading admin explanation: {str(e)}")

            # Fixed response editing functionality (moved below metadata)
            st.write("")  # Add some spacing
            st.markdown('<div class="mini-header">Fixed Response</div>', unsafe_allow_html=True)

            # Get existing fixed response using backend
            try:
                # This is expected to be a list of response dictionaries
                raw_responses_data = self.backend.get_post_fixed_responses(post_id)
            except Exception as e:
                raw_responses_data = None # Ensure it's None on error
                st.error(f"Error loading fixed responses: {str(e)}")

            # Create tabs for existing and adding responses
            exist_tab, add_tab = st.tabs(["Existing", "Add New"])

            with exist_tab:
                fixed_responses_to_display = []
                if isinstance(raw_responses_data, list):
                    fixed_responses_to_display = raw_responses_data
                elif isinstance(raw_responses_data, dict) and raw_responses_data: # Handle if backend returns a single dict
                    fixed_responses_to_display = [raw_responses_data]

                if not fixed_responses_to_display:
                    st.info("No fixed responses exist for this post. Use the 'Add New' tab to create one.")
                else:
                    for index, response_item in enumerate(fixed_responses_to_display):
                        if not isinstance(response_item, dict):
                            st.warning(f"Skipping an invalid fixed response item (item {index + 1}).")
                            continue

                        st.markdown("---") # Visual separator for each response
                        # Use a unique key for each form, including post_id and index
                        form_key = f"existing_response_form_{post_id}_{index}"
                        original_trigger_keyword = response_item.get("trigger_keyword", "")

                        with st.form(key=form_key, border=True):
                            st.markdown(f"**Response for Trigger: \"{original_trigger_keyword}\"**" if original_trigger_keyword else f"**Response Item {index+1}**")

                            trigger_keyword_input = st.text_input(
                                "Trigger keyword",
                                value=original_trigger_keyword,
                                key=f"trigger_{form_key}"
                            )
                            comment_response_input = st.text_area(
                                "Comment reply",
                                value=response_item.get("comment_response_text", ""),
                                key=f"comment_{form_key}"
                            )
                            dm_response_input = st.text_area(
                                "DM reply",
                                value=response_item.get("direct_response_text", ""),
                                key=f"dm_{form_key}"
                            )

                            # Row for buttons
                            col_update, col_delete = st.columns(2)
                            with col_update:
                                update_button = st.form_submit_button(f"{self.const.ICONS['save']} Update This Response", width='stretch')
                            with col_delete:
                                delete_button = st.form_submit_button(
                                    f"{self.const.ICONS['delete']} Remove This Response",
                                    type="secondary",
                                    width='stretch'
                                )

                            if update_button:
                                new_trigger_keyword = trigger_keyword_input.strip()
                                if not new_trigger_keyword:
                                    st.error("Trigger keyword is required.")
                                else:
                                    success = self.backend.create_or_update_post_fixed_response(
                                        post_id=post_id,
                                        trigger_keyword=new_trigger_keyword,
                                        comment_response_text=comment_response_input.strip() or None,
                                        direct_response_text=dm_response_input.strip() or None
                                    )
                                    if success:
                                        st.success(f"Response for '{new_trigger_keyword}' processed successfully!")
                                        if original_trigger_keyword and original_trigger_keyword != new_trigger_keyword:
                                            st.info(f"Content previously associated with '{original_trigger_keyword}' is now under '{new_trigger_keyword}'. The old trigger entry might still exist if not explicitly managed by the backend as a 'rename'.")
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to process response for '{new_trigger_keyword}'.")

                            if delete_button:
                                if not original_trigger_keyword:
                                    st.error("Cannot delete response: Original trigger keyword is missing.")
                                else:
                                    try:
                                        success = self.backend.delete_post_fixed_response(post_id, original_trigger_keyword)
                                        if success:
                                            st.success(f"Response for '{original_trigger_keyword}' removed successfully.")
                                            st.rerun()
                                        else:
                                            st.error(f"Failed to remove response for '{original_trigger_keyword}'.")
                                    except Exception as e:
                                        st.error(f"Error removing response: {str(e)}")

            with add_tab:
                # Form for adding new fixed response
                try:
                    # Set up form
                    with st.form(key=f"new_response_form_{post_id}", border=False):

                        # Trigger keyword
                        new_trigger_keyword = st.text_input(
                            "Trigger keyword",
                            placeholder="Enter words that will trigger this response"
                        )

                        # Comment response
                        new_comment_response = st.text_area(
                            "Comment reply",
                            placeholder="Response to post when someone comments with trigger words"
                        )

                        # Direct message response
                        new_dm_response = st.text_area(
                            "DM reply",
                            placeholder="Response sent as DM when someone messages with trigger words"
                        )

                        # Submit button to save fixed response
                        new_submit_button = st.form_submit_button(f"{self.const.ICONS['add']} Create", width='stretch')

                        if new_submit_button:
                            # Handle adding new fixed response using backend
                            try:
                                if new_trigger_keyword.strip():
                                    new_success = self.backend.create_or_update_post_fixed_response(
                                        post_id=post_id,
                                        trigger_keyword=new_trigger_keyword.strip(),
                                        comment_response_text=new_comment_response.strip() if new_comment_response.strip() else None,
                                        direct_response_text=new_dm_response.strip() if new_dm_response.strip() else None
                                    )
                                    if new_success:
                                        st.success(f"{self.const.ICONS['success']} Created!")
                                        st.rerun()
                                else:
                                    st.error("Trigger keyword is required")
                            except Exception as e:
                                st.error(f"{self.const.ICONS['error']} Error creating: {str(e)}")

                except Exception as e:
                    st.error(f"Error loading form: {str(e)}")
