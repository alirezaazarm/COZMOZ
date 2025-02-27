from flask import Blueprint, request, jsonify
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, UTC
import logging
import json
from ..services.img_search import process_image
from ..utils.helpers import download_image, handle_message, check_content_type, handle_comment, get_db
from ..config import Config

logger = logging.getLogger(__name__)

webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return handle_webhook_verification()

    elif request.method == 'POST':
        return handle_webhook_post()


def handle_webhook_verification():
    hub_verify_token = request.args.get('hub.verify_token')
    hub_challenge = request.args.get('hub.challenge')

    if not hub_verify_token or not hub_challenge:
        logger.warning("Missing required parameters for verification")
        return "Missing parameters", 400

    if hub_verify_token == Config.VERIFY_TOKEN:
        logger.info("Successfully verified webhook")
        return hub_challenge, 200

    logger.warning("Invalid verification token attempt")
    return "Invalid verification token", 403


def handle_webhook_post():
    logger.info("Webhook POST received")
    data = request.json
    logger.debug(f"Raw payload:\n{json.dumps(data, indent=2)}")
    success_count = 0
    failure_count = 0

    with get_db() as db:
        try:
            entries = data.get('entry', [])
            logger.info(f"Processing {len(entries)} entries")

            for entry in entries:
                messaging_events = entry.get('messaging', [])
                logger.info(f"Processing {len(messaging_events)} messaging events")
                for event in messaging_events:
                    try:
                        if process_event(db, event):
                            success_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        logger.error(f"Event processing failed: {str(e)}", exc_info=True)
                        failure_count += 1
                        db.rollback()

                comment_events = entry.get('changes', [])
                logger.info(f"Processing {len(comment_events)} changes")
                for change in comment_events:
                    try:
                        if process_comment_event(db, change):
                            success_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        logger.error(f"Change processing failed: {str(e)}", exc_info=True)
                        failure_count += 1
                        db.rollback()

            logger.info(f"Processed {success_count} events successfully, {failure_count} failures")
            return jsonify({
                "status": "success",
                "processed": success_count,
                "failed": failure_count
            }), 200

        except SQLAlchemyError as e:
            logger.error(f"Database error: {str(e)}")
            db.rollback()
            return jsonify({"status": "error", "message": "Database operation failed"}), 500

        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            db.rollback()
            return jsonify({"status": "error", "message": "Internal server error"}), 500

        finally:
            db.expire_all()
            logger.debug("Database connection closed")


def process_event(db, event):
    sender_id = event['sender']['id']
    recipient_id = event['recipient']['id']
    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000, UTC).replace(tzinfo=None)

    if event.get('message', {}).get('is_echo'):
        logger.debug("Skipping echo message")
        return False

    if 'message' in event:
        return process_message_event(db, event, sender_id, recipient_id, timestamp)

    elif 'reaction' in event:
        return process_reaction_event(db, event, sender_id, recipient_id, timestamp)

    else:
        logger.warning(f"Unhandled event type: {list(event.keys())}")
        return False


def process_message_event(db, event, sender_id, recipient_id, timestamp):
    logger.debug("Processing message event")
    message = event['message']

    message_data = {
        'id': message['mid'],
        'from': {
            'id': sender_id,
            'username': f"ig_user_{sender_id}",
            'full_name': '',
            'profile_picture_url': ''
        },
        'recipient_id': recipient_id,
        'text': message.get('text'),
        'timestamp': timestamp
    }

    attachments = message.get('attachments', [])
    if attachments:
        first_attachment = attachments[0]
        message_data['media_type'] = first_attachment.get('type')
        message_data['media_url'] = first_attachment.get('payload', {}).get('url')
        attachments_type = first_attachment.get('type')

        if attachments_type in ['ig_reel', 'ig_post']:
            title = first_attachment.get('payload', {}).get('title', 'No Title')
            message_data['text'] = f"Instagram shared reel caption: {title}"

        elif attachments_type == "share":
            shared_content_type = check_content_type(message_data['media_url'])

            if shared_content_type == 'image':
                message_data['media_type'] += '_image'
                image = download_image(message_data['media_url'])
                message_data['text'] = process_image(image)

        if message_data['media_type'] == 'image':
            image = download_image(message_data['media_url'])
            if image:
                message_data['text'] = process_image(image)

    return handle_message(db, message_data)


def process_comment_event(db, change):
    if change.get('field') == 'comments':
        comment_data = change.get('value', {})
        from_user = comment_data.get('from', {})
        media = comment_data.get('media', {})
        comment_text = comment_data.get('text', '')
        comment_id = comment_data.get('id', '')
        parent_comment_id = comment_data.get('parent_id')
        created_time = comment_data.get('created_time', 0)
        try:
            timestamp = datetime.fromtimestamp(created_time, UTC).replace(tzinfo=None)
        except Exception as e:
            logger.error(f"Failed to parse timestamp for comment {comment_id}: {str(e)}")
            timestamp = datetime.now(UTC)

        if handle_comment(db, {
            'comment_id': comment_id,
            'post_id': media.get('id'),
            'user_id': from_user.get('id'),
            'username': from_user.get('username'),
            'comment_text': comment_text,
            'parent_comment_id': parent_comment_id,
            'timestamp': timestamp,
            'status': 'not_replied'
        }):
            return True
        else:
            return False
    else:
        logger.warning(f"Unhandled change event type: {change.get('field')}")
        return False


def process_reaction_event(db, event, sender_id, recipient_id, timestamp):
    logger.debug("Processing reaction event")
    reaction = event['reaction']

    reaction_data = {
        'id': reaction['mid'],
        'from': {
            'id': sender_id,
            'username': f"ig_user_{sender_id}"
        },
        'content_type': 'message',
        'content_id': reaction['mid'],
        'reaction_type': reaction.get('emoji', 'unknown'),
        'timestamp': timestamp
    }

    return handle_reaction(db, reaction_data)


def handle_reaction(db, reaction_data):
    try:
        logger.info(f"Handling reaction: {reaction_data}")
        return True
    except Exception as e:
        logger.error(f"Failed to handle reaction: {str(e)}")
        return False