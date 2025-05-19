from flask import Blueprint, request, jsonify
from pymongo.errors import PyMongoError
from datetime import datetime, timezone
import logging
import json
from ..services.img_search import process_image
from ..services.instagram_service import InstagramService
from ..utils.helpers import get_db
from ..config import Config
from ..models.enums import MessageRole

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

                comment_events = entry.get('changes', [])
                entry_time = entry.get('time')
                logger.info(f"Processing {len(comment_events)} changes")
                for change in comment_events:
                    try:
                        if process_comment_event(db, change, entry_time):
                            success_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        logger.error(f"Change processing failed: {str(e)}", exc_info=True)
                        failure_count += 1

            logger.info(f"Processed {success_count} events successfully, {failure_count} failures")
            return jsonify({
                "status": "success",
                "processed": success_count,
                "failed": failure_count
            }), 200

        except PyMongoError as e:
            logger.error(f"Database error: {str(e)}")
            return jsonify({"status": "error", "message": "Database operation failed"}), 500

        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": "Internal server error"}), 500

        finally:
            logger.debug("Database operation completed")


def process_event(db, event):
    sender_id = event['sender']['id']
    # We don't need to use the recipient_id as it's always the main account
    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000, timezone.utc).replace(tzinfo=None)

    # Check if this is an echo message (from business account)
    is_echo = event.get('message', {}).get('is_echo', False)

    # Get app settings directly from the instagram_service module to ensure we have the latest
    from ..services.instagram_service import APP_SETTINGS

    # Get the current assistant setting
    is_assistant_enabled = APP_SETTINGS.get('assistant', True)

    # Explicitly check if the value is a string and convert accordingly
    if isinstance(is_assistant_enabled, str):
        is_assistant_enabled = is_assistant_enabled.lower() == 'true'

    logger.info(f"Webhook - Processing event with assistant {'ENABLED' if is_assistant_enabled else 'DISABLED'}")
    logger.debug(f"Webhook - APP_SETTINGS: {APP_SETTINGS}")
    logger.debug(f"Processing event: sender_id={sender_id}, is_echo={is_echo}, is_assistant_enabled={is_assistant_enabled}, CONFIG.PAGE_ID={Config.PAGE_ID}")
    logger.debug(f"Is sender business account? {sender_id == Config.PAGE_ID}")

    # Echo message handling:
    if is_echo:
        # When the echo is from our page ID
        if sender_id == Config.PAGE_ID:
            # If assistant is enabled, skip all page echoes (bot replies)
            if is_assistant_enabled:
                logger.debug(f"Assistant enabled - Skipping echo message from business account (ID: {sender_id})")
                return True
            else:
                # When assistant is disabled, we WANT to process these as admin replies
                logger.debug(f"Assistant disabled - Processing admin echo message (ID: {sender_id})")
                # Process the message as an admin reply
                if 'message' in event:
                    process_result = process_message_event(db, event, sender_id, timestamp)
                    logger.debug(f"Process message result for admin echo: {process_result}")
                    return process_result
                return False
        else:
            # Handle other echo message logic
            if is_assistant_enabled:
                logger.debug("Assistant is enabled - Skipping echo message")
                return False
            else:
                logger.debug("Assistant is disabled - Processing admin echo message")

    if 'message' in event:
        return process_message_event(db, event, sender_id, timestamp)
    elif 'reaction' in event:
        return process_reaction_event(db, event, sender_id, timestamp)
    else:
        logger.warning(f"Unhandled event type: {list(event.keys())}")
        return False


def process_message_event(db, event, sender_id, timestamp):
    logger.debug(f"Processing message event. sender_id={sender_id}, timestamp={timestamp}")
    try:
        message = event['message']
        logger.debug(f"Message data from event: {message}")

        # Check if this is an echo message from business account
        is_echo = message.get('is_echo', False)
        is_business_account = sender_id == Config.PAGE_ID

        # Get latest app settings
        from ..services.instagram_service import APP_SETTINGS
        is_assistant_enabled = APP_SETTINGS.get('assistant', True)

        # Ensure boolean conversion
        if isinstance(is_assistant_enabled, str):
            is_assistant_enabled = is_assistant_enabled.lower() == 'true'

        logger.debug(f"Message analysis: is_echo={is_echo}, is_business_account={is_business_account}, is_assistant_enabled={is_assistant_enabled}")

        # For echo messages, extract the recipient (actual user we're talking to)
        recipient_id = None
        if is_echo and is_business_account:
            recipient_id = event.get('recipient', {}).get('id')
            logger.info(f"Echo message with recipient_id: {recipient_id}")

        # Determine the correct role
        message_role = MessageRole.USER.value
        if is_echo and is_business_account:
            message_role = MessageRole.ADMIN.value if not is_assistant_enabled else MessageRole.ASSISTANT.value
            logger.info(f"Echo message from business account. Setting role to {message_role}")

        message_data = {
            'id': message['mid'],
            'from': {
                'id': sender_id
            },
            'text': message.get('text'),
            'timestamp': timestamp,
            'is_echo': is_echo,
            'role': message_role
        }

        if recipient_id:
            message_data['recipient'] = {
                'id': recipient_id
            }
            logger.info(f"Added recipient ID {recipient_id} to message data for echo message")

        logger.info(f"Message data initialized: {message_data}")

        attachments = message.get('attachments', [])
        if attachments:
            logger.info(f"Found {len(attachments)} attachment(s) in the message.")
            first_attachment = attachments[0]
            message_data['media_type'] = first_attachment.get('type')
            message_data['media_url'] = first_attachment.get('payload', {}).get('url')
            attachments_type = first_attachment.get('type')

            logger.info(f"Attachment type: {attachments_type}, Media URL: {message_data['media_url']}")

            # If this is a story reply, check for fixed response
            if attachments_type == 'story':
                story_id = first_attachment.get('payload', {}).get('story_id') or first_attachment.get('payload', {}).get('id')
                trigger_keyword = message.get('text')
                user_id = sender_id
                logger.info(f"Checking for story fixed response: story_id={story_id}, trigger_keyword={trigger_keyword}, user_id={user_id}")
                handled = InstagramService.handle_story_reply(db, story_id, trigger_keyword, user_id)
                logger.info(f"Story fixed response handled: {handled}")
                return handled
            elif attachments_type in ['ig_reel', 'ig_post']:
                title = first_attachment.get('payload', {}).get('title', 'No Title')
                cover_image = InstagramService.download_image(message_data['media_url'])
                if cover_image:
                    logger.info("Image downloaded successfully.")
                    label = process_image(cover_image)
                    message_data['text'] = f"Instagram shared reel caption: {title}\n" + "vision model similarity search results: " + label
                    logger.info(f"Updated message text with reel caption: {message_data['text']}")
                else:
                    logger.error("Failed to download image.")
                    message_data['text'] = f"Instagram shared reel caption: {title}\n"

            elif attachments_type == "share":
                logger.info("Processing shared content.")
                shared_content_type = InstagramService.check_content_type(message_data['media_url'])

                if shared_content_type == 'image':
                    logger.info("Shared content is an image.")
                    message_data['media_type'] += '_image'
                    image = InstagramService.download_image(message_data['media_url'])
                    if image:
                        logger.info("Image downloaded successfully.")
                        message_data['text'] = process_image(image)
                        logger.info(f"Updated message text with processed image: {message_data['text']}")
                    else:
                        logger.error("Failed to download image.")

            if message_data['media_type'] == 'image':
                logger.info("Processing standalone image attachment.")
                image = InstagramService.download_image(message_data['media_url'])
                if image:
                    logger.info("Image downloaded successfully.")
                    message_data['text'] = process_image(image)
                    logger.info(f"Updated message text with processed image: {message_data['text']}")
                else:
                    logger.error("Failed to download image.")

        logger.info(f"Final message data: {message_data}")
        logger.info("Message event processed successfully. Passing to handle_message.")
        result = InstagramService.handle_message(db, message_data)
        logger.info(f"InstagramService.handle_message result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error processing message event: {str(e)}", exc_info=True)
        raise


def process_comment_event(db, change, entry_time=None):
    if change.get('field') == 'comments':
        comment_data = change.get('value', {})
        from_user = comment_data.get('from', {})
        media = comment_data.get('media', {})
        comment_text = comment_data.get('text', '')
        comment_id = comment_data.get('id', '')
        parent_comment_id = comment_data.get('parent_id')
        created_time = comment_data.get('created_time')
        if created_time:
            try:
                timestamp = datetime.fromtimestamp(created_time, timezone.utc)
            except Exception as e:
                logger.error(f"Failed to parse timestamp for comment {comment_id}: {str(e)}")
                timestamp = datetime.now(timezone.utc)
        elif entry_time:
            try:
                timestamp = datetime.fromtimestamp(entry_time, timezone.utc)
            except Exception as e:
                logger.error(f"Failed to parse entry_time for comment {comment_id}: {str(e)}")
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        # Check if this comment is from the business account (echo comment)
        from_id = from_user.get('id')
        if from_id == Config.PAGE_ID:
            logger.info(f"Skipping echo comment from business account (ID: {from_id})")
            return True

        try:
            if InstagramService.handle_comment(db, {
                'comment_id': comment_id,
                'post_id': media.get('id'),
                'user_id': from_user.get('id'),
                'username': from_user.get('username'),
                'comment_text': comment_text,
                'parent_id': parent_comment_id,
                'timestamp': timestamp,
                'status': 'not_replied'
            }):
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Error processing comment event: {str(e)}", exc_info=True)
            return False
    else:
        logger.warning(f"Unhandled change event type: {change.get('field')}")
        return False


def process_reaction_event(db, event, sender_id, timestamp):
    logger.debug("Processing reaction event")
    reaction = event['reaction']

    reaction_data = {
        'id': reaction['mid'],
        'from': {
            'id': sender_id,
            'username': f"{sender_id}"
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