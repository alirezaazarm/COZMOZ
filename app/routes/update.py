from flask import Blueprint, request, jsonify
from ..config import Config
from ..utils.helpers import allowed_file, secure_filename_wrapper
from ..services.instagram_service import APP_SETTINGS, COMMENT_FIXED_RESPONSES, STORY_FIXED_RESPONSES, IG_CONTENT_IDS, InstagramService
from ..services.openai_service import OpenAIService
import os
import logging

logger = logging.getLogger(__name__)

update_bp = Blueprint('update', __name__, url_prefix='/update')

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
            settings['assistant'] = APP_SETTINGS.get('assistant', False)
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
        assistant_enabled = APP_SETTINGS.get('assistant', False)
        if isinstance(assistant_enabled, str):
            assistant_enabled = assistant_enabled.lower() == 'true'
        logger.info(f"Assistant is {'ENABLED' if assistant_enabled else 'DISABLED'}")

        # Update the service's global variable
        result = InstagramService.set_app_settings(settings)
        if not result:
            logger.error("Failed to update Instagram service app settings")
            return False

        result = OpenAIService.set_vs_id(settings)
        if not result:
            logger.error("appsetting to main failed to give vs_id")
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
@update_bp.route('/fixed-responses/comments', methods=['POST'])
def update_comment_fixed_responses():
    """Update comment fixed responses in memory."""
    logger.info("Received request to update comment fixed responses.")
    auth_error = authenticate()
    if auth_error:
        return auth_error

    if request.method == 'POST':
        data = request.json
        if not isinstance(data, dict):
            logger.error("Invalid data format for comment fixed responses. Expected a dictionary.")
            return jsonify({'error': 'Invalid data format, expected a dictionary mapping post IDs to responses.'}), 400
        InstagramService.set_comment_fixed_responses(data)
        logger.info(f"Updated COMMENT_FIXED_RESPONSES: {COMMENT_FIXED_RESPONSES}")
        return jsonify({'message': 'Comment fixed responses updated successfully.'}), 200
    else:
        logger.error("Invalid request method for updating comment fixed responses.")
        return jsonify({'message': 'Request method is wrong!'}), 405

@update_bp.route('/fixed-responses/stories', methods=['POST'])
def update_story_fixed_responses():
    """Update story fixed responses in memory."""
    logger.info("Received request to update story fixed responses.")
    auth_error = authenticate()
    if auth_error:
        return auth_error

    if request.method == 'POST':
        data = request.json
        if not isinstance(data, dict):
            logger.error("Invalid data format for story fixed responses. Expected a dictionary.")
            return jsonify({'error': 'Invalid data format, expected a dictionary mapping story IDs to responses.'}), 400
        InstagramService.set_story_fixed_responses(data)
        logger.info(f"Updated STORY_FIXED_RESPONSES: {STORY_FIXED_RESPONSES}")
        return jsonify({'message': 'Story fixed responses updated successfully.'}), 200
    else:
        logger.error("Invalid request method for updating story fixed responses.")
        return jsonify({'message': 'Request method is wrong!'}), 405

# ============================ IG CONTENCT UPDATE ================================= #
@update_bp.route('/ig-content-ids', methods=['POST'])
def update_ig_content_ids():
    """Update IG content IDs in memory."""
    logger.info("Received request to update IG content IDs.")
    auth_error = authenticate()
    if auth_error:
        return auth_error

    if request.method == 'POST':
        data = request.json
        if not isinstance(data, dict):
            logger.error("Invalid data format for IG content IDs. Expected a dictionary.")
            return jsonify({'error': 'Invalid data format, expected a dictionary mapping post IDs to content IDs.'}), 400
        InstagramService.set_ig_content_ids(data)
        logger.info(f"Updated IG_CONTENT_IDS: {IG_CONTENT_IDS}")
        return jsonify({'message': 'IG content IDs updated successfully.'}), 200
    else:
        logger.error("Invalid request method for updating IG content IDs.")
        return jsonify({'message': 'Request method is wrong!'}), 405