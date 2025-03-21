from flask import Blueprint, request, jsonify
from ..config import Config
from ..utils.helpers import allowed_file, secure_filename_wrapper, en_to_fa_number, en_to_ar_number
from ..services.instagram_service import InstagramService
import os
import logging

logger = logging.getLogger(__name__)

# Global variables to hold in-memory settings and responses
COMMENT_FIXED_RESPONSES = {}
DIRECT_FIXED_RESPONSES = {}
APP_SETTINGS = {}

update_bp = Blueprint('update', __name__, url_prefix='/update')

# Function to reload fixed responses in memory
def reload_fixed_responses(fixed_responses, incoming):
    """Load fixed responses into memory for quick access"""
    try:
        comment = {}
        direct = {}

        for resp in fixed_responses:
            trigger_keyword = str(resp['trigger_keyword'])

            if incoming == 'Comment':
                comment[trigger_keyword] = {'comment': resp['comment_response_text'], 'DM': resp['direct_response_text']}
                comment[en_to_fa_number(trigger_keyword)] = {'comment': resp['comment_response_text'], 'DM': resp['direct_response_text']}
                comment[en_to_ar_number(trigger_keyword)] = {'comment': resp['comment_response_text'], 'DM': resp['direct_response_text']}

            if incoming == "Direct":
                direct[trigger_keyword] = {'DM': resp['direct_response_text']}
                direct[en_to_fa_number(trigger_keyword)] = {'DM': resp['direct_response_text']}
                direct[en_to_ar_number(trigger_keyword)] = {'DM': resp['direct_response_text']}

        if incoming == 'Comment':
            global COMMENT_FIXED_RESPONSES
            COMMENT_FIXED_RESPONSES = comment
            # Update the service's global variable
            InstagramService.set_fixed_responses('Comment', comment)

        if incoming == "Direct":
            global DIRECT_FIXED_RESPONSES
            DIRECT_FIXED_RESPONSES = direct
            # Update the service's global variable
            InstagramService.set_fixed_responses('Direct', direct)

        logger.info(f"Fixed responses for {incoming} reloaded successfully")
        return True
    except Exception as e:
        logger.error(f"Error occurred when reloading fixed responses: {str(e)}")
        return False

# Function to reload app settings in memory
def reload_app_settings(app_settings):
    """Load app settings into memory for quick access"""
    try:
        settings = {}
        for setting in app_settings:
            for key, value in setting.items():
                # Convert string to actual boolean if it's a string representation of a boolean
                if isinstance(value, str) and value.lower() in ['true', 'false']:
                    settings[key] = value.lower() == 'true'
                else:
                    settings[key] = value

        global APP_SETTINGS
        # Log the previous settings for comparison
        logger.info(f"Previous app settings: {APP_SETTINGS}")
        
        # Ensure the assistant key is always present
        if 'assistant' not in settings:
            # Keep the previous value if it exists, otherwise default to True
            settings['assistant'] = APP_SETTINGS.get('assistant', True)
            logger.info(f"Added missing 'assistant' key with value: {settings['assistant']}")
        
        # Ensure assistant value is always a boolean
        if isinstance(settings['assistant'], str):
            settings['assistant'] = settings['assistant'].lower() == 'true'
            logger.info(f"Converted assistant setting from string to boolean: {settings['assistant']}")
        
        # Update the settings
        APP_SETTINGS = settings
        
        # Log the new settings to verify the update
        logger.info(f"New app settings: {APP_SETTINGS}")
        
        # Explicitly log the assistant setting
        assistant_enabled = APP_SETTINGS.get('assistant', True)
        if isinstance(assistant_enabled, str):
            assistant_enabled = assistant_enabled.lower() == 'true'
        logger.info(f"Assistant is {'ENABLED' if assistant_enabled else 'DISABLED'}")
        
        # Update the service's global variable
        result = InstagramService.set_app_settings(settings)
        
        if not result:
            logger.error("Failed to update Instagram service app settings")
            return False
            
        logger.info(f"App settings reloaded successfully: {settings}")
        return True
    except Exception as e:
        logger.error(f"Error occurred when reloading app settings: {str(e)}")
        return False

def authenticate():
    """Authenticate requests using the verify token."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        logger.warning("Missing or invalid Authorization header")
        return jsonify({'message': 'Unauthorized'}), 401
    
    token = auth_header.split('Bearer ')[1]
    if token != Config.VERIFY_TOKEN:
        logger.warning("Invalid token provided")
        return jsonify({'message': 'Unauthorized'}), 401
    
    return None  # Authentication successful

# =========================== MODEL UPDATE =================================== #
@update_bp.route('/model', methods=['POST'])
def update_model():
    """Handle model file upload."""
    logger.info("Received request to update model.")
    auth_error = authenticate()
    if auth_error:
        return auth_error

    file = request.files.get('file')
    if not file or file.filename == '':
        logger.error("No file selected for upload.")
        return jsonify({'error': 'No selected file'}), 400

    if allowed_file(file.filename):
        filename = secure_filename_wrapper(file.filename)
        save_path = os.path.join('/root/cozmoz_application/from_colab', filename)
        try:
            file.save(save_path)
            logger.info(f"File {filename} uploaded successfully to {save_path}.")
            return jsonify({'message': f'File {filename} uploaded successfully'}), 200
        except Exception as e:
            logger.error(f"Error saving file {filename}: {str(e)}")
            return jsonify({'error': 'Failed to save file'}), 500
    else:
        logger.error(f"File type not allowed: {file.filename}.")
        return jsonify({'error': 'File type not allowed'}), 400

# ============================ APP SETTINGS UPDATE ================================= #
@update_bp.route('/app-settings', methods=['POST'])
def update_app_settings():
    """Handle app settings update."""
    logger.info("Received request to update app settings.")
    auth_error = authenticate()
    if auth_error:
        return auth_error

    if request.method == 'POST':
        try:
            app_settings = request.json
            logger.info(f"Received app settings data: {app_settings}")
            
            # Validate input data
            if not app_settings:
                logger.error("No app settings data provided")
                return jsonify({'message': 'No app settings data provided'}), 400
                
            # Convert to expected format if not already a list
            if not isinstance(app_settings, list):
                logger.warning("App settings data is not a list, attempting to convert")
                if isinstance(app_settings, dict):
                    app_settings = [app_settings]
                else:
                    logger.error(f"Invalid app settings data format: {type(app_settings)}")
                    return jsonify({'message': 'Invalid data format, must be a list or dictionary'}), 400
            
            # Pre-process boolean values to ensure consistent format
            for setting in app_settings:
                for key, value in setting.items():
                    if isinstance(value, str) and value.lower() in ['true', 'false']:
                        setting[key] = value.lower() == 'true'
                        logger.debug(f"Converted string value '{value}' to boolean {setting[key]} for key '{key}'")
            
            # Use the centralized reload function
            success = reload_app_settings(app_settings)
            
            if success:
                # Get the latest settings after update
                logger.info(f"App settings updated successfully. Current settings: {APP_SETTINGS}")
                
                # Explicitly log the assistant setting
                assistant_enabled = APP_SETTINGS.get('assistant', True)
                if isinstance(assistant_enabled, str):
                    assistant_enabled = assistant_enabled.lower() == 'true'
                logger.info(f"Assistant is now {'ENABLED' if assistant_enabled else 'DISABLED'}")
                
                return jsonify({'message': 'app settings updated successfully', 'settings': APP_SETTINGS}), 200
            else:
                logger.error("Failed to reload app settings")
                return jsonify({'error': 'Failed to update app settings'}), 500
            
        except Exception as e:
            logger.error(f"Error updating app settings: {str(e)}")
            return jsonify({'error': f'Failed to update app settings: {str(e)}'}), 500
    else:
        logger.error("Invalid request method for updating app settings.")
        return jsonify({'message': 'request method is wrong!'}), 405

# ============================ FIXED RESPONSE UPDATE ================================= #
@update_bp.route('/fixed-responses', methods=['POST'])
def update_fixed_responses():
    """Handle fixed responses update."""
    logger.info("Received request to update fixed responses.")
    auth_error = authenticate()
    if auth_error:
        return auth_error

    if request.method == 'POST':
        data = request.json
        incoming = data.get("incoming")
        if incoming:
            try:
                reload_fixed_responses(data["fixed_responses"], incoming)
                logger.info("Fixed responses updated successfully.")
                return jsonify({'message': 'fixed responses updated successfully'}), 200
            except Exception as e:
                logger.error(f"Error updating fixed responses: {str(e)}")
                return jsonify({'error': 'Failed to update fixed responses'}), 500
        else:
            logger.error("Missing 'incoming' field in request.")
            return jsonify({'message': 'the <incoming> is missing!'}), 400
    else:
        logger.error("Invalid request method for updating fixed responses.")
        return jsonify({'message': 'request method is wrong!'}), 405