from flask import Blueprint, request, jsonify
from ..config import Config
from ..utils.helpers import allowed_file, secure_filename_wrapper, load_main_app_globals_from_db
import os
import logging

logger = logging.getLogger(__name__)

update_bp = Blueprint('/hooshang_update', __name__, url_prefix='/hooshang_update')

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

# ============================ MEMORY RELOAD ================================= #
@update_bp.route('/reload-memory', methods=['POST'])
def reload_memory():
    """Reload all main app memory from the database."""
    logger.info("Received request to reload main app memory from DB.")
    auth_error = authenticate()
    if auth_error:
        return auth_error
    try:
        load_main_app_globals_from_db()
        logger.info("Main app memory reloaded from DB successfully.")
        return jsonify({'message': 'Main app memory reloaded from DB successfully.'}), 200
    except Exception as e:
        logger.error(f"Error reloading main app memory: {str(e)}")
        return jsonify({'error': f'Failed to reload main app memory: {str(e)}'}), 500