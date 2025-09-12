from flask import Blueprint, request, jsonify
from pymongo.errors import PyMongoError
from datetime import datetime, timezone
import logging
import json
import requests
from ..services.platforms.instagram import InstagramService
from ..services.platforms.telegram import TelegramService
from ..utils.helpers import get_db
from ..utils.helpers import (
    get_client_username_by_ig_id,
    get_client_by_ig_id,
    set_ig_id_to_client,
    get_app_settings,
    get_client_credentials,
)
from ..config import Config
from ..models.enums import MessageRole, UserStatus, ModuleType

logger = logging.getLogger(__name__)

instagram_webhook_bp = Blueprint('instagram_webhook', __name__)
telegram_webhook_bp = Blueprint('telegram_webhook', __name__)

@instagram_webhook_bp.route('/instagram', methods=['GET'])
def instagram_webhook_verify():
    """Instagram webhook verification endpoint (GET)."""
    return verify_instagram_webhook()


@instagram_webhook_bp.route('/instagram', methods=['POST'])
def instagram_webhook():
    """Instagram webhook endpoint (POST)."""
    return handle_instagram_webhook_post()
@telegram_webhook_bp.route('/telegram/<client_username>', methods=['POST'])
def telegram_webhook(client_username):
    """Telegram webhook endpoint per client. Configure Telegram bot webhook URL to point here."""
    try:
        data = request.get_json(silent=True) or {}
        with get_db() as db:
            ok = TelegramService.handle_update(db, data, client_username)
            if ok:
                return jsonify({"ok": True}), 200
            return jsonify({"ok": False}), 200  # Telegram requires 200 even on soft failure
    except Exception as e:
        logger.error(f"Telegram webhook error for {client_username}: {str(e)}", exc_info=True)
        # Return 200 to avoid Telegram retry storm, but include ok False
        return jsonify({"ok": False}), 200

@telegram_webhook_bp.route('/telegram/<client_username>/set', methods=['POST'])
def telegram_set_webhook(client_username):
    """Programmatically set Telegram webhook for a client using stored bot token."""
    try:
        # Determine target URL
        body = request.get_json(silent=True) or {}
        override_url = body.get('url') or request.args.get('url')
        target_url = override_url or f"{Config.BASE_URL}/telegram/{client_username}"

        # Get bot token from client credentials
        creds = TelegramService.get_client_credentials(client_username)
        token = creds.get('telegram_access_token') if creds else None
        if not token:
            logger.error(f"No Telegram token for client: {client_username}")
            return jsonify({"ok": False, "error": "missing_token"}), 400

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": target_url},
            timeout=20
        )
        data = resp.json() if resp.content else {"ok": False}
        status = 200 if data.get('ok') else 400
        return jsonify({"ok": data.get('ok', False), "result": data}), status
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook for {client_username}: {str(e)}", exc_info=True)
        return jsonify({"ok": False, "error": "exception"}), 500

@telegram_webhook_bp.route('/telegram/<client_username>/info', methods=['GET'])
def telegram_webhook_info(client_username):
    """Get Telegram webhook info for a client's bot."""
    try:
        creds = TelegramService.get_client_credentials(client_username)
        token = creds.get('telegram_access_token') if creds else None
        if not token:
            return jsonify({"ok": False, "error": "missing_token"}), 400
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getWebhookInfo",
            timeout=20
        )
        data = resp.json() if resp.content else {"ok": False}
        status = 200 if data.get('ok') else 400
        return jsonify({"ok": data.get('ok', False), "result": data}), status
    except Exception as e:
        logger.error(f"Failed to get Telegram webhook info for {client_username}: {str(e)}", exc_info=True)
        return jsonify({"ok": False, "error": "exception"}), 500

@telegram_webhook_bp.route('/telegram/<client_username>/delete', methods=['POST'])
def telegram_delete_webhook(client_username):
    """Delete Telegram webhook for a client's bot."""
    try:
        body = request.get_json(silent=True) or {}
        drop = body.get('drop_pending_updates')
        if drop is None:
            drop = request.args.get('drop_pending_updates', 'true').lower() == 'true'

        creds = TelegramService.get_client_credentials(client_username)
        token = creds.get('telegram_access_token') if creds else None
        if not token:
            return jsonify({"ok": False, "error": "missing_token"}), 400

        params = {"drop_pending_updates": bool(drop)}
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/deleteWebhook",
            data=params,
            timeout=20
        )
        data = resp.json() if resp.content else {"ok": False}
        status = 200 if data.get('ok') else 400
        return jsonify({"ok": data.get('ok', False), "result": data}), status
    except Exception as e:
        logger.error(f"Failed to delete Telegram webhook for {client_username}: {str(e)}", exc_info=True)
        return jsonify({"ok": False, "error": "exception"}), 500


def verify_instagram_webhook():
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

def handle_instagram_webhook_post():
    logger.info("Webhook POST received")
    data = request.json
    logger.debug(f"Raw payload:\n{json.dumps(data, indent=2)}")
    success_count = 0
    failure_count = 0

    with get_db() as db:
        try:
            entries = data.get('entry', [])
            logger.info(f"Processing {len(entries)} entries")

            # Iterate over each entry
            for entry in entries:
                # Identify the client based on the entry ID (which should be the ig_id)
                entry_id = entry.get('id')
                if not entry_id:
                    logger.error("Entry missing ID - cannot identify client")
                    failure_count += 1
                    continue

                # Find the client by ig_id
                client_username = get_client_username_by_ig_id(entry_id)
                if not client_username:
                    # fallback: load from DB, then update in-memory mapping
                    client_username = get_client_by_ig_id(entry_id)
                    if client_username:
                        set_ig_id_to_client(entry_id, client_username)
                if not client_username:
                    logger.error(f"No client found for ig_id: {entry_id}")
                    failure_count += 1
                    continue

                logger.info(f"Processing entry for client: {client_username} (ig_id: {entry_id})")

                messaging_events = entry.get('messaging', [])
                logger.info(f"Processing {len(messaging_events)} messaging events for client: {client_username}")

                # Handle all message events, including echoes
                for event in messaging_events:
                    if 'message' not in event:
                        logger.info(f"Ignoring non-message event: {list(event.keys())}")
                        continue

                    # Convert raw timestamp (milliseconds) to datetime with tzinfo
                    raw_ts = event.get('timestamp')
                    if isinstance(raw_ts, int):
                        timestamp = datetime.fromtimestamp(raw_ts / 1000.0, tz=timezone.utc)
                    else:
                        timestamp = raw_ts  # assume already datetime

                    try:
                        if process_instagram_message_event(db, event, event['sender']['id'], timestamp, client_username):
                            success_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        logger.error(f"Message event processing failed: {e}", exc_info=True)
                        failure_count += 1

                # Process comment change events if present
                comment_events = entry.get('changes', [])
                entry_time = entry.get('time')
                logger.info(f"Processing {len(comment_events)} changes for client: {client_username}")
                for change in comment_events:
                    try:
                        if process_instagram_comment_event(db, change, entry_time, client_username):
                            success_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        logger.error(f"Change processing failed: {e}", exc_info=True)
                        failure_count += 1

            logger.info(f"Processed {success_count} events successfully, {failure_count} failures")
            return jsonify({
                "status": "success",
                "processed": success_count,
                "failed": failure_count
            }), 200

        except PyMongoError as e:
            logger.error(f"Database error: {e}")
            return jsonify({"status": "error", "message": "Database operation failed"}), 500

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return jsonify({"status": "error", "message": "Internal server error"}), 500

        finally:
            logger.debug("Database operation completed")


def process_instagram_event(db, event, client_username):
    try:
        sender_id = event['sender']['id']
        timestamp = datetime.fromtimestamp(event['timestamp'] / 1000, timezone.utc).replace(tzinfo=None)

        # Check if this is an echo message (from business account)
        is_echo = event.get('message', {}).get('is_echo', False)

        # Get client-specific app settings
        app_settings = get_app_settings(client_username)
        is_assistant_enabled = app_settings.get(ModuleType.DM_ASSIST.value, True)

        # Explicitly check if the value is a string and convert accordingly
        if isinstance(is_assistant_enabled, str):
            is_assistant_enabled = is_assistant_enabled.lower() == 'true'

        # Get client credentials to check business account ID
        client_creds = get_client_credentials(client_username)
        if not client_creds:
            logger.error(f"No credentials found for client: {client_username}")
            return False

        client_page_id = client_creds.get('ig_id')
        if not client_page_id:
            logger.error(f"No ig_id found for client: {client_username}")
            return False

        logger.info(f"Webhook - Processing event for client {client_username} with assistant {'ENABLED' if is_assistant_enabled else 'DISABLED'}")
        logger.debug(f"Processing event: sender_id={sender_id}, is_echo={is_echo}, is_assistant_enabled={is_assistant_enabled}, client_page_id={client_page_id}")
        logger.debug(f"Is sender business account? {sender_id == client_page_id}")

        # Echo message handling:
        if is_echo:
            # When the echo is from our client's page ID
            if sender_id == client_page_id:
                # If assistant is enabled, skip all page echoes (bot replies)
                if is_assistant_enabled:
                    logger.debug(f"Assistant enabled - Skipping echo message from business account (ID: {sender_id})")
                    return True
                else:
                    # When assistant is disabled, we WANT to process these as admin replies
                    logger.debug(f"Assistant disabled - Processing admin echo message (ID: {sender_id})")
                    # Process the message as an admin reply
                    if 'message' in event:
                        process_result = process_instagram_message_event(db, event, sender_id, timestamp, client_username)
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
            return process_instagram_message_event(db, event, sender_id, timestamp, client_username)
        elif 'reaction' in event:
            # Reactions handling can be added later if needed; ignore for now
            logger.info("Ignoring reaction event for Instagram")
            return True
        else:
            logger.warning(f"Unhandled event type: {list(event.keys())}")
            return False

    except KeyError as ke:
        logger.error(f"Missing required key in event data: {str(ke)}")
        logger.error(f"Event data: {json.dumps(event, indent=2)}")
        return False
    except Exception as e:
        logger.error(f"Error in process_event: {str(e)}", exc_info=True)
        return False


def process_instagram_message_event(db, event, sender_id, timestamp, client_username):
    """
    Processes incoming Instagram messaging events, including story replies, story mentions, and other attachments.
    Delegates fixed-response logic to InstagramService.handle_shared_content and falls back to standard processing.
    Returns True if processed successfully or fixed-response triggered, False on error or failure.
    """
    logger.debug(f"Processing message event for client {client_username}. sender_id={sender_id}, timestamp={timestamp}")
    try:
        message = event['message']
        logger.debug(f"Message data from event: {message}")

        # Get client credentials to check business account ID
        client_creds = get_client_credentials(client_username)
        if not client_creds:
            logger.error(f"No credentials found for client: {client_username}")
            return False

        client_page_id = client_creds.get('ig_id')
        if not client_page_id:
            logger.error(f"No ig_id found for client: {client_username}")
            return False

        # Check if this is an echo message from business account
        is_echo = message.get('is_echo', False)
        is_business_account = sender_id == client_page_id

        # Get client-specific app settings
        app_settings = get_app_settings(client_username)
        is_assistant_enabled = app_settings.get(ModuleType.DM_ASSIST.value, True)

        # Ensure boolean conversion
        if isinstance(is_assistant_enabled, str):
            is_assistant_enabled = is_assistant_enabled.lower() == 'true'

        logger.debug(f"Message analysis for client {client_username}: is_echo={is_echo}, is_business_account={is_business_account}, is_assistant_enabled={is_assistant_enabled}")

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

        # Initialize message_data
        message_data = {
            'id': message['mid'],
            'from': {'id': sender_id},
            'text': message.get('text'),
            'timestamp': timestamp,
            'is_echo': is_echo,
            'role': message_role
        }
        if recipient_id:
            message_data['recipient'] = {'id': recipient_id}
            logger.info(f"Added recipient ID {recipient_id} to message data for echo message")

        logger.info(f"Message data initialized: {message_data}")

        # 1) Handle story replies
        if 'reply_to' in message and isinstance(message['reply_to'], dict) and 'story' in message['reply_to']:
            # Ensure user exists before processing story reply
            if not is_echo:  # Only for non-echo messages (actual user messages)
                user_info = {'id': sender_id, 'username': ''}
                InstagramService.process_user(user_info, UserStatus.WAITING.value, client_username)
                logger.info(f"Ensured user {sender_id} exists for story reply processing for client {client_username}")
            
            story_payload = message['reply_to']['story']
            attachment = {
                'type': 'story_reply',
                'payload': {
                    'id': story_payload.get('id'),
                    'url': story_payload.get('url'),
                    'title': story_payload.get('title', None),
                    'user_message': message.get('text')
                }
            }
            trigger_text = message.get('text')
            result = InstagramService.handle_shared_content(
                db=db,
                attachment=attachment,
                client_username=client_username,
                user_id=sender_id,
                trigger_keyword=trigger_text
            )
            # If fixed response triggered, skip further processing
            if result is None:
                logger.info(f"Story-reply fixed response sent for user {sender_id} for client {client_username}")
                return True
            if result:
                message_data['text'] = result
                logger.info(f"Updated message text from story_reply: {result}")

        # 2) Handle regular attachments
        attachments = message.get('attachments', [])
        if attachments:
            logger.info(f"Found {len(attachments)} attachment(s) in the message.")
            
            # Filter out template media types
            filtered_attachments = []
            for attachment in attachments:
                # Check both payload.media_type and attachment.type for template
                media_type = attachment.get('payload', {}).get('media_type')
                attachment_type = attachment.get('type', '')
                
                if media_type == 'template' or attachment_type == 'template':
                    logger.info(f"Ignoring attachment with media_type '{media_type}' or type '{attachment_type}' (template)")
                    continue
                    
                # Also check if the attachment payload has template-related fields
                payload = attachment.get('payload', {})
                if payload.get('template_type') or 'template' in str(payload).lower():
                    logger.info(f"Ignoring template-related attachment: {payload}")
                    continue
                    
                filtered_attachments.append(attachment)
            
            if not filtered_attachments:
                logger.info("All attachments were templates, skipping attachment processing")
                # Continue to process text message if any
            else:
                # Process each attachment separately and store each one individually
                attachment_results = []
                fixed_response_triggered = False
                
                for i, attachment in enumerate(filtered_attachments):
                    attachment_type = attachment.get('type', 'unknown')
                    attachment_url = attachment.get('payload', {}).get('url', 'no_url')
                    logger.info(f"Processing attachment {i+1}/{len(filtered_attachments)}: type={attachment_type}, url={attachment_url}")
                    
                    # Check for fixed response on first attachment only (to maintain existing behavior)
                    if i == 0:
                        logger.info(f"Checking for fixed response on first attachment")
                        result = InstagramService.handle_shared_content(
                            db=db,
                            attachment=attachment,
                            client_username=client_username,
                            user_id=sender_id,
                            trigger_keyword=message.get('text')
                        )
                        if result is None:
                            logger.info("Attachment handled via fixed response. Skipping further message processing.")
                            fixed_response_triggered = True
                            break
                    else:
                        # For subsequent attachments, process without fixed response check
                        logger.info(f"Processing subsequent attachment {i+1} without fixed response check")
                        result = InstagramService.handle_shared_content(
                            db=db,
                            attachment=attachment,
                            client_username=client_username,
                            user_id=sender_id,
                            trigger_keyword=None  # No fixed response for subsequent attachments
                        )
                    
                    logger.info(f"Attachment {i+1} processing result: {result}")
                    
                    # Store each attachment as a separate message in the database with its own analysis
                    attachment_message_id = f"{message['mid']}_attachment_{i}"
                    attachment_message_data = {
                        'id': attachment_message_id,
                        'from': {'id': sender_id},
                        'text': result if result else f"Attachment {i+1}: {attachment_type}",
                        'timestamp': timestamp,
                        'is_echo': is_echo,
                        'role': message_role,
                        'media_type': attachment_type,
                        'media_url': attachment_url if attachment_url != 'no_url' else None
                    }
                    if recipient_id:
                        attachment_message_data['recipient'] = {'id': recipient_id}
                    
                    logger.info(f"Storing attachment message with ID: {attachment_message_id}")
                    
                    # Store this attachment message separately with its individual analysis
                    success = InstagramService.handle_message(db, attachment_message_data, client_username)
                    if success:
                        logger.info(f"Successfully stored attachment {i+1} with analysis: {result}")
                        if result:
                            attachment_results.append(f"Image {i+1}: {result}")
                    else:
                        logger.error(f"Failed to store attachment {i+1} for message {message['mid']}")
                
                if fixed_response_triggered:
                    return True
                
                # If we have attachments, we've already stored each one individually
                # Only store the main message if it has text content (without attachment analyses)
                if message_data.get('text') and message_data['text'].strip():
                    # Store the original text message without attachment analyses
                    text_message_data = {
                        'id': message['mid'],
                        'from': {'id': sender_id},
                        'text': message.get('text'),  # Original text only
                        'timestamp': timestamp,
                        'is_echo': is_echo,
                        'role': message_role
                    }
                    if recipient_id:
                        text_message_data['recipient'] = {'id': recipient_id}
                    
                    success = InstagramService.handle_message(db, text_message_data, client_username)
                    if success:
                        logger.info(f"Successfully stored original text message: {message.get('text')}")
                    else:
                        logger.error(f"Failed to store original text message")
                
                logger.info(f"Processed {len(filtered_attachments)} attachments individually.")
                return True

        # 3) Handle messages without attachments - route to standard message handling
        success = InstagramService.handle_message(db, message_data, client_username)
        if success:
            logger.info(f"Successfully processed message {message_data['id']} from user {sender_id}")
            return True
        else:
            logger.error(f"Failed to process message {message_data['id']} from user {sender_id}")
            return False

    except KeyError as ke:
        logger.error(f"Missing required key in message event: {str(ke)}")
        logger.error(f"Event data: {json.dumps(event, indent=2)}")
        return False
    except Exception as e:
        logger.error(f"Error processing message event: {str(e)}", exc_info=True)
        return False


def process_instagram_comment_event(db, change, entry_time=None, client_username=None):
    try:
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
            # Use client-specific page ID for echo detection
            client_page_id = None
            if client_username:
                client_creds = get_client_credentials(client_username)
                if client_creds:
                    client_page_id = client_creds.get('ig_id')
            if from_id == client_page_id:
                logger.info(f"Skipping echo comment from business account (ID: {from_id}) for client {client_username}")
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
                }, client_username=client_username):
                    return True
                else:
                    return False
            except Exception as e:
                logger.error(f"Error processing comment event: {str(e)}", exc_info=True)
                return False
        else:
            logger.warning(f"Unhandled change event type: {change.get('field')}")
            return False

    except Exception as e:
        logger.error(f"Error in process_comment_event: {str(e)}", exc_info=True)
        return False
