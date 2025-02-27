from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from ..config import Config
from ..utils.helpers import allowed_file
import os
import logging
from ..utils.helpers import reload_fixed_responses

logger = logging.getLogger(__name__)

update_bp = Blueprint('update', __name__, url_prefix='/update')


def authenticate():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "Missing Authorization header"}), 401

    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Invalid Authorization header format"}), 401

    token = auth_header.split(" ")[1]
    if token != Config.VERIFY_TOKEN:
        return jsonify({"error": "Invalid API key"}), 401

    return None

# =========================== MODEL UPDATE =================================== #
@update_bp.route('/model', methods=['POST'])
def update_model():
    auth_error = authenticate()
    if auth_error:
        return auth_error

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join('/root/cozmoz_application/from_colab', filename)
        file.save(save_path)
        return jsonify({'message': f'File {filename} uploaded successfully'}), 200

    return jsonify({'error': 'File type not allowed'}), 400

# ============================ FIXED RESPONSE UPDATE ================================= #
@update_bp.route('/fixed-responses', methods=['POST'])
def update_fixed_responses():
    auth_error = authenticate()
    if auth_error:
        return auth_error

    if request.method == 'POST':
        data = request.json
        incoming = data.get("incoming")
        if incoming:
            reload_fixed_responses(data["fixed_responses"], incoming)
            return jsonify({'message': 'fixed responses updated successfully'}), 200
        else:
            return jsonify({'message': 'the <incoming> is missing!'})

    else:
        return jsonify({'message': 'request method is wrong!'})

# ============================== APP SETTING UPDATE =================================== #
@update_bp.route('/app-settings', methods=['POST'])
def update_app_setting():
    auth_error = authenticate()
    if auth_error:
        return auth_error

    if request.method == 'POST':
        data = request.json
        print(data)
        return jsonify({'message': 'app settings updated successfully'}), 200
    else:
        return jsonify({'message': 'request method is wrong!'})