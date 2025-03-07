import logging
from datetime import datetime, timezone
from ..models.appsettings import AppSettings
from ..models.fixedresponse import FixedResponse
from ..models.base import SessionLocal
from ..models.product import Product
from ..config import Config
import requests
import json

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
            with SessionLocal() as db:
                products = db.query(Product).all()
                products_data = [
                    {
                        "ID": p.pID,
                        "Title": p.title,
                        "Price": json.loads(p.price) if isinstance(p.price, dict) else p.price,
                        "Additional info": json.loads(p.additional_info) if isinstance(p.additional_info, dict) else p.additional_info,
                        "Category": p.category,
                        "Stock status" : p.stock_status,
                        "Translated Title": p.translated_title,
                        "Link": p.link
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
            with SessionLocal() as db:
                setting = db.query(AppSettings).all()
                setting = [{s.key:s.value} for s in setting]

                response = requests.post(self.app_setting_url, headers=self.headers, json=setting)
                if response.status_code == 200:
                    logger.info("App settings successfully sent to the main server.")
                    return True
                else:
                    logger.error(f"Failed to send app settings. Status code: {response.status_code}")
                    logger.debug(f"Settings data: {setting}")
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
            with SessionLocal() as db:
                setting = db.query(AppSettings).filter(AppSettings.key == key).first()
                logger.info(f"App setting for key '{key}' fetched successfully.")
                return setting.value if setting else None
        except Exception as e:
            logger.error(f"Error in get_app_setting for key '{key}': {str(e)}")
            return {"error in get_app_setting calling": str(e)}

    def update_is_active(self, key, value):
        logger.info(f"Updating app setting for key: {key} with value: {value}.")
        try:
            with SessionLocal() as db:
                setting = db.query(AppSettings).filter(AppSettings.key == key).first()
                if not setting:
                    setting = AppSettings(key=key, value=value)
                    db.add(setting)
                    logger.info(f"New app setting created for key: {key}.")
                else:
                    setting.value = value
                    logger.info(f"App setting updated for key: {key}.")
                db.commit()
            self.app_settings_to_main()
        except Exception as e:
            logger.error(f"Error in update_is_active for key '{key}': {str(e)}")
            return {"error in update_is_active": str(e)}

    def get_fixed_responses(self, incoming=None):
        logger.info(f"Fetching fixed responses for incoming type: {incoming}.")
        try:
            with SessionLocal() as db:
                responses = db.query(FixedResponse).filter(FixedResponse.incoming == incoming).all()
                responses = [
                    {
                        "id": r.id,
                        "trigger_keyword": r.trigger_keyword,
                        "comment_response_text": r.comment_response_text,
                        "direct_response_text": r.direct_response_text,
                        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S.%f") if r.updated_at else None
                    }
                    for r in responses
                ]
                logger.info(f"Successfully fetched {len(responses)} fixed responses.")
                self.fixedresponses_to_main(responses, incoming)
                return responses
        except Exception as e:
            logger.error(f"Failed to fetch fixed responses for incoming type '{incoming}': {str(e)}")
            raise RuntimeError(f"Failed to fetch fixed responses: {str(e)}")

    def add_fixed_response(self, trigger, comment_response_text, direct_response_text, incoming):
        logger.info(f"Adding new fixed response for trigger: {trigger} and incoming type: {incoming}.")
        try:
            with SessionLocal() as db:
                new_response = FixedResponse(
                    trigger_keyword=trigger,
                    comment_response_text=comment_response_text if incoming == "Comment" else None,
                    direct_response_text=direct_response_text,
                    incoming=incoming,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(new_response)
                db.commit()
                db.refresh(new_response)
                logger.info(f"Fixed response added successfully with ID: {new_response.id}.")
                return new_response.id
        except Exception as e:
            logger.error(f"Failed to add fixed response: {str(e)}")
            raise RuntimeError(f"Failed to add fixed response: {str(e)}")

    def update_fixed_response(self, response_id, trigger, comment_response_text, direct_response_text, incoming):
        logger.info(f"Updating fixed response with ID: {response_id}.")
        try:
            with SessionLocal() as db:
                response = db.query(FixedResponse).filter(FixedResponse.id == response_id).first()
                if response:
                    response.trigger_keyword = trigger
                    response.comment_response_text = comment_response_text if incoming == "Comment" else None,
                    response.direct_response_text = direct_response_text
                    response.incoming = incoming
                    response.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(response)
                    logger.info(f"Fixed response with ID {response_id} updated successfully.")
                return True
        except Exception as e:
            logger.error(f"Failed to update fixed response with ID {response_id}: {str(e)}")
            raise RuntimeError(f"Failed to update fixed response: {str(e)}")

    def delete_fixed_response(self, response_id):
        logger.info(f"Deleting fixed response with ID: {response_id}.")
        try:
            with SessionLocal() as db:
                response = db.query(FixedResponse).filter(FixedResponse.id == response_id).first()
                if response:
                    db.delete(response)
                    db.commit()
                    logger.info(f"Fixed response with ID {response_id} deleted successfully.")
                return True
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
            with SessionLocal() as db:
                vs_setting = db.query(AppSettings).filter_by(key='vs_id').first()
                if vs_setting:
                    logger.info(f"Current vector store ID: {vs_setting.value}")
                    return vs_setting.value
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
            result = openai_service.connect_assistant_to_vs()
            if result['success']:
                logger.info("Assistant connected to vector store successfully.")
                return result
            else:
                logger.warning(f"Failed to connect assistant to vector store: {result['message']}")
                return result
        except Exception as e:
            logger.error(f"Error connecting assistant to vector store: {str(e)}")
            return {'success': False, 'message': str(e)}