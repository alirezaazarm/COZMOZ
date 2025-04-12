import logging
from datetime import datetime, timezone
from ..models.appsettings import AppSettings
from ..models.fixedresponse import FixedResponse
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

logger = logging.getLogger(__name__)

class Backend:
    def __init__(self):
        self.fixed_responses_url = Config.BASE_URL + "/update/fixed-responses"
        self.app_setting_url = Config.BASE_URL + "/update/app-settings"
        self.headers = {"Content-Type": "application/json",  "Authorization": f"Bearer {Config.VERIFY_TOKEN}" }
        self.scraper = CozmozScraper()
        logger.info("Backend initialized with configuration URLs and headers.")

    # ------------------------------------------------------------------
    # Product scraping
    # ------------------------------------------------------------------
    def update_products(self):
        logger.info("Scraping the site is starting...")
        try:
            self.scraper.update_products()
            logger.info("Update products completed.")
        except Exception as e:
            logger.error(f"Failed to update products: {str(e)}", exc_info=True)
            raise

        logger.info("Rebuilding files and vector store is starting...")
        try:
            openai_service = OpenAIService()
            result = openai_service.rebuild_files_and_vector_store()
            if result:
                logger.info("Files and vector store rebuilt successfully")
                return True
            else:
                logger.error("Failed to rebuild files and vector store")
                return False
        except Exception as e:
            logger.error(f"Error in rebuild_files_and_vector_store: {str(e)}")
            return False

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
                    "Translated Title": p['translated_title'],
                    "Link": p['link']
                }
                for p in products
            ]
            logger.info(f"Successfully fetched {len(products_data)} products.")
            return products_data
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return []

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
            setting_list = [{s['key']: s['value']} for s in settings]

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

    def fixedresponses_to_main(self, fixedresponses, incoming):
        logger.info(f"Sending fixed responses to the main server for incoming type: {incoming}.")
        data = {"fixed_responses":fixedresponses, "incoming":incoming}
        response = requests.post(self.fixed_responses_url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info("Fixed responses successfully sent to the main server.")
            return True
        else:
            logger.error(f"Request failed with status code: {response.status_code}")
            logger.error(f"Response text: {response.text}")
            return False

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

    def get_fixed_responses(self, incoming=None):
        logger.info(f"Fetching fixed responses for incoming type: {incoming}.")
        try:
            # Use the MongoDB FixedResponse model directly
            # Find all responses with matching incoming type
            responses = []
            all_responses = FixedResponse.get_all()
            for r in all_responses:
                if r['incoming'] == incoming:
                    responses.append({
                        "id": str(r['_id']),
                        "trigger_keyword": r['trigger_keyword'],
                        "comment_response_text": r['comment_response_text'],
                        "direct_response_text": r['direct_response_text'],
                        "updated_at": r['updated_at'].strftime("%Y-%m-%d %H:%M:%S.%f") if r['updated_at'] else None
                    })

            logger.info(f"Successfully fetched {len(responses)} fixed responses.")
            self.fixedresponses_to_main(responses, incoming)
            return responses
        except Exception as e:
            logger.error(f"Failed to fetch fixed responses for incoming type '{incoming}': {str(e)}")
            raise RuntimeError(f"Failed to fetch fixed responses: {str(e)}")

    def add_fixed_response(self, trigger, comment_response_text, direct_response_text, incoming):
        logger.info(f"Adding new fixed response for trigger: {trigger} and incoming type: {incoming}.")
        try:
            # Use the MongoDB FixedResponse model directly
            new_response = FixedResponse.create(
                incoming=incoming,
                trigger_keyword=trigger,
                comment_response_text=comment_response_text if incoming == "Comment" else None,
                direct_response_text=direct_response_text
            )

            if new_response:
                logger.info(f"Fixed response added successfully with ID: {new_response['_id']}.")
                return str(new_response['_id'])
            else:
                logger.error("Failed to add fixed response.")
                return None
        except Exception as e:
            logger.error(f"Failed to add fixed response: {str(e)}")
            raise RuntimeError(f"Failed to add fixed response: {str(e)}")

    def update_fixed_response(self, response_id, trigger, comment_response_text, direct_response_text, incoming):
        logger.info(f"Updating fixed response with ID: {response_id}.")
        try:
            # Use the MongoDB FixedResponse model directly
            update_data = {
                "trigger_keyword": trigger,
                "comment_response_text": comment_response_text if incoming == "Comment" else None,
                "direct_response_text": direct_response_text,
                "incoming": incoming
            }

            result = FixedResponse.update(response_id, update_data)
            if result:
                logger.info(f"Fixed response with ID {response_id} updated successfully.")
            else:
                logger.warning(f"No changes made to fixed response with ID {response_id}.")
            return result
        except Exception as e:
            logger.error(f"Failed to update fixed response with ID {response_id}: {str(e)}")
            raise RuntimeError(f"Failed to update fixed response: {str(e)}")

    def delete_fixed_response(self, response_id):
        logger.info(f"Deleting fixed response with ID: {response_id}.")
        try:
            # Use the MongoDB FixedResponse model directly
            result = FixedResponse.delete(response_id)
            if result:
                logger.info(f"Fixed response with ID {response_id} deleted successfully.")
            else:
                logger.warning(f"Fixed response with ID {response_id} not found or could not be deleted.")
            return result
        except Exception as e:
            logger.error(f"Failed to delete fixed response with ID {response_id}: {str(e)}")
            raise RuntimeError(f"Failed to delete fixed response: {str(e)}")

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

    def get_current_vs_id(self):
        """Get the current vector store ID from the database."""
        logger.info("Fetching current vector store ID.")
        try:
            # Use the MongoDB AppSettings model directly
            vs_setting = AppSettings.get_by_key('vs_id')
            if vs_setting:
                logger.info(f"Current vector store ID: {vs_setting['value']}")
                return vs_setting['value']
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
            openai_service = OpenAIService()
            instructions = openai_service.get_assistant_instructions()
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
            openai_service = OpenAIService()
            temperature = openai_service.get_assistant_temperature()
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
            openai_service = OpenAIService()
            top_p = openai_service.get_assistant_top_p()
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
            openai_service = OpenAIService()
            result = openai_service.update_assistant_instructions(new_instructions)
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
            openai_service = OpenAIService()
            result = openai_service.update_assistant_temperature(new_temperature)
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
            openai_service = OpenAIService()
            result = openai_service.update_assistant_top_p(new_top_p)
            if result['success']:
                logger.info("Assistant top_p updated successfully.")
                return result
            else:
                logger.warning(f"Failed to update assistant top_p: {result['message']}")
                return result
        except Exception as e:
            logger.error(f"Error updating assistant top_p: {str(e)}")
            return {'success': False, 'message': str(e)}

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
                    predicted_label = process_image(pil_image, top_k=5)

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

    def create_chat_thread(self):
        """
        Creates a new chat thread via OpenAIService.
        Returns the thread ID on success, raises an exception on failure.
        """
        logger.info("Creating new chat thread.")
        try:
            openai_service = OpenAIService()
            thread_id = openai_service.create_thread()
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
            openai_service = OpenAIService()
            response = openai_service.send_message_to_thread(thread_id, user_message)
            logger.info(f"Message sent to thread {thread_id} successfully.")
            return response
        except Exception as e:
            logger.error(f"Failed to send message to thread {thread_id}: {str(e)}", exc_info=True)
            raise
    def translate_titles(self):
        """Translate product titles using OpenAI"""
        logger.info("Starting product title translation")
        try:
            openai_service = OpenAIService()
            result = openai_service.translate_titles()
            if result:
                logger.info("Product titles translated successfully")
                return True
            else:
                logger.error("Failed to translate product titles")
                return False
        except Exception as e:
            logger.error(f"Error in translate_titles: {str(e)}")
            return False
    def process_uploaded_image(self, image_bytes, top_k=5):
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
                analysis_result = process_image(pil_image, top_k=top_k)
                logger.info(f"Image processing result: {analysis_result}")
                return analysis_result

            except Image.UnidentifiedImageError:
                logger.error("Could not identify image file. It might be corrupted or not an image.")
                return "Error: Could not read image file. Please upload a valid image."
            except Exception as e:
                logger.error(f"Error processing uploaded image in backend: {str(e)}", exc_info=True)
                # Return a generic error message to the UI
                return f"Error: An unexpected error occurred while processing the image."