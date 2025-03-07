from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from ..config import Config
from ..utils.helpers import allowed_file, reload_fixed_responses, reload_app_settings
import os
import logging

logger = logging.getLogger(__name__)

update_bp = Blueprint('update', __name__, url_prefix='/update')

def authenticate():
    """Authenticate the request using the Authorization header."""
    logger.debug("Authenticating request.")
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        logger.error("Missing Authorization header.")
        return jsonify({"error": "Missing Authorization header"}), 401

    if not auth_header.startswith("Bearer "):
        logger.error("Invalid Authorization header format.")
        return jsonify({"error": "Invalid Authorization header format"}), 401

    token = auth_header.split(" ")[1]
    if token != Config.VERIFY_TOKEN:
        logger.error("Invalid API key provided.")
        return jsonify({"error": "Invalid API key"}), 401

    logger.debug("Authentication successful.")
    return None

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
        filename = secure_filename(file.filename)
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

# ============================== APP SETTING UPDATE =================================== #
@update_bp.route('/app-settings', methods=['POST'])
def update_app_setting():
    """Handle app settings update."""
    logger.info("Received request to update app settings.")
    auth_error = authenticate()
    if auth_error:
        return auth_error

    if request.method == 'POST':
        data = request.json
        logger.debug(f"Received app settings data: {data}")
        try:
            if not isinstance(data, list):
                logger.error("Invalid app settings format - expected a list")
                return jsonify({'error': 'Invalid app settings format'}), 400

            success = reload_app_settings(data)
            if success:
                logger.info("App settings updated successfully.")
                return jsonify({'message': 'app settings updated successfully'}), 200
            else:
                logger.error("Failed to update app settings")
                return jsonify({'error': 'Failed to update app settings'}), 500
        except Exception as e:
            logger.error(f"Error updating app settings: {str(e)}")
            return jsonify({'error': 'Failed to update app settings'}), 500
    else:
        logger.error("Invalid request method for updating app settings.")
        return jsonify({'message': 'request method is wrong!'}), 405