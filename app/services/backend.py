import logging
from datetime import datetime, timezone
from ..models.appsettings import AppSettings
from ..models.fixedresponse import FixedResponse
from ..models.product import Product
from ..config import Config
import requests

logger = logging.getLogger(__name__)

class Backend:
    def __init__(self):
        self.fixed_responses_url = Config.BASE_URL + "/update/fixed-responses"
        self.app_setting_url = Config.BASE_URL + "/update/app-settings"
        self.headers = {"Content-Type": "application/json",  "Authorization": f"Bearer {Config.VERIFY_TOKEN}" }
        logger.info("Backend initialized with configuration URLs and headers.")

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
        from ..services.openai_service import OpenAIService

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

    def update_assistant_instructions(self, new_instructions):
        """Update the instructions for the assistant."""
        from ..services.openai_service import OpenAIService

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

    def connect_assistant_to_vs(self):
        """Connect the assistant to the current vector store."""
        from ..services.openai_service import OpenAIService

        logger.info("Connecting assistant to vector store.")
        try:
            openai_service = OpenAIService()
            result = openai_service.update_or_create_vs()

            if result['success']:
                # After successful vector store creation, connect it to the assistant
                assistant_result = openai_service.update_assistant_instructions(
                    openai_service.get_assistant_instructions()
                )

                if assistant_result['success']:
                    logger.info("Assistant connected to vector store successfully.")
                    # Return combined result with logs
                    return {
                        'success': True,
                        'message': f"Created vector store with {result['processed_count']} of {result['total_count']} products and connected to assistant.",
                        'vector_store_id': result.get('vector_store_id'),
                        'processed_count': result.get('processed_count'),
                        'total_count': result.get('total_count'),
                        'logs': result.get('logs', [])
                    }
                else:
                    logger.warning(f"Vector store created but failed to update assistant: {assistant_result['message']}")
                    return {
                        'success': True,
                        'message': f"Vector store created successfully but failed to update assistant: {assistant_result['message']}",
                        'vector_store_id': result.get('vector_store_id'),
                        'processed_count': result.get('processed_count'),
                        'total_count': result.get('total_count'),
                        'logs': result.get('logs', [])
                    }
            else:
                logger.warning(f"Failed to create vector store: {result['message']}")
                return {
                    'success': False,
                    'message': result['message'],
                    'logs': result.get('logs', [])
                }
        except Exception as e:
            logger.error(f"Error connecting assistant to vector store: {str(e)}", exc_info=True)
            return {'success': False, 'message': str(e), 'logs': [f"Error: {str(e)}"]}