import logging
from datetime import datetime, timezone
import requests
from io import BytesIO
from PIL import Image
from ...models.user import User
from ...models.enums import UserStatus, MessageRole, ModuleType
from ...models.client import Client
from ...utils import helpers
from ..AI.img_search import process_image


logger = logging.getLogger(__name__)


class TelegramService:
    @staticmethod
    def _get_file_url(token, file_id):
        """Resolve Telegram file_id to a downloadable file URL."""
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file_id},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return None
            file_path = data.get("result", {}).get("file_path")
            if not file_path:
                return None
            return f"https://api.telegram.org/file/bot{token}/{file_path}"
        except Exception:
            return None
    @staticmethod
    def _download_image(url):
        """Download an image from a URL and return a PIL Image, or None on failure."""
        try:
            if not url:
                raise ValueError("No URL provided")
            response = requests.get(
                url,
                stream=True,
                timeout=15
            )
            response.raise_for_status()
            return Image.open(BytesIO(response.content))
        except Exception as e:
            logger.error(f"Telegram image download failed: {str(e)}")
            return None
    @staticmethod
    def get_client_credentials(client_username):
        """Prefer in-memory credentials; fall back to DB and cache when missing."""
        try:
            creds = helpers.get_client_credentials(client_username)
            # Ensure we actually have Telegram token cached; otherwise fetch and cache
            if creds and creds.get('telegram_access_token'):
                return creds
            db_creds = Client.get_client_credentials(client_username)
            if db_creds:
                helpers.set_client_credentials(db_creds, client_username)
            return db_creds
        except Exception as e:
            logger.error(f"Failed to get credentials for client {client_username}: {str(e)}")
            return None

    @staticmethod
    def get_client_credentials_from_db(client_username):
        """Get client credentials for a specific client directly from the database."""
        try:
            return Client.get_client_credentials(client_username)
        except Exception as e:
            logger.error(f"Failed to get Telegram credentials for client {client_username}: {str(e)}")
            return None

    @staticmethod
    def _get_user_profile_photo_url(token, user_id):
        """
        Fetch the user's profile photo URL from Telegram.
        Returns the URL of the highest resolution photo, or None.
        """
        try:
            api_url = f"https://api.telegram.org/bot{token}/getUserProfilePhotos"
            params = {"user_id": user_id, "limit": 1}
            resp = requests.get(api_url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("ok") or not data.get("result", {}).get("photos"):
                return None

            # Get the highest resolution photo (last in the list)
            highest_res_photo = data["result"]["photos"][0][-1]
            file_id = highest_res_photo.get("file_id")

            if not file_id:
                return None

            # Use the existing helper to get the final downloadable URL
            return TelegramService._get_file_url(token, file_id)

        except Exception as e:
            logger.error(f"Failed to get user profile photo for {user_id}: {str(e)}")
            return None

    @staticmethod
    def send_message(chat_id, text, client_username=None):
        """Send a message to a Telegram chat using the client's bot token."""
        try:
            if not client_username:
                logger.error("Telegram send_message requires client_username context")
                return None

            # Prefer cached credentials
            creds = TelegramService.get_client_credentials(client_username)
            if not creds or not creds.get('telegram_access_token'):
                logger.error(f"No Telegram token for client: {client_username}")
                return None

            token = creds['telegram_access_token']
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            ok = data.get('ok', False)
            if not ok:
                logger.error(f"Telegram send failed for client {client_username}: {data}")
                return None
            message_id = data.get('result', {}).get('message_id')
            return message_id
        except Exception as e:
            logger.error(f"Telegram send failed: {str(e)}", exc_info=True)
            return None


    @staticmethod
    def broadcast_message(text, client_username, batch_size=50, delay_between_batches=1, image_url=None):
        """
        broadcast message to all Telegram users for a specific client.

        This method:
        - Retrieves all Telegram users for the given client
        - Sends the message to each user with error handling
        - Stores the broadcast message in each user's history with proper role
        - Updates user status according to business rules
        - Processes users in batches to avoid rate limiting
        - Returns statistics on success/failure

        Args:
            text (str): The message text to broadcast.
            client_username (str): The client whose users should receive the message.
            batch_size (int): Number of messages to send before pausing. Default: 50.
            delay_between_batches (int): Seconds to wait between batches. Default: 1.
            image_url (str, optional): URL of image to attach to broadcast. Default: None.

        Returns:
            dict: Statistics dictionary with:
                    - 'total_users': Total number of users targeted
                    - 'successful': Number of messages sent successfully
                    - 'failed': Number of failed sends
                    - 'failed_users': List of user IDs that failed
                    - 'errors': List of error messages
        """
        import time

        try:
            logger.info(f"Starting broadcast to all Telegram users for client {client_username}")

            # 1. Retrieve all Telegram users for this client
            try:
                users = User.get_users_by_platform_for_client(
                    platform="telegram",
                    client_username=client_username
                )
            except Exception as e:
                logger.error(f"Failed to retrieve Telegram users: {str(e)}")
                return {
                    'total_users': 0,
                    'successful': 0,
                    'failed': 0,
                    'failed_users': [],
                    'errors': [f"Failed to retrieve users: {str(e)}"]
                }

            if not users:
                logger.info(f"No Telegram users found for client {client_username}")
                return {
                    'total_users': 0,
                    'successful': 0,
                    'failed': 0,
                    'failed_users': [],
                    'errors': []
                }

            # 2. Get credentials once for efficiency
            creds = TelegramService.get_client_credentials(client_username)
            if not creds or not creds.get('telegram_access_token'):
                logger.error(f"No Telegram token for client: {client_username}")
                return {
                    'total_users': len(users),
                    'successful': 0,
                    'failed': len(users),
                    'failed_users': [user['user_id'] for user in users],
                    'errors': [f"No Telegram token available for client {client_username}"]
                }

            token = creds['telegram_access_token']

            # 3. Send messages with batching for rate limiting
            successful = 0
            failed = 0
            failed_users = []
            errors = []

            for index, user in enumerate(users):
                try:
                    user_id = user.get('user_id')
                    if not user_id:
                        failed += 1
                        errors.append("User missing user_id")
                        continue

                    # Get current user status before sending
                    current_user = User.get_by_id(user_id, client_username)
                    current_status = current_user.get('status') if current_user else UserStatus.WAITING.value

                    # Send the message (with or without image)
                    if image_url:
                        # Send photo with caption
                        url = f"https://api.telegram.org/bot{token}/sendPhoto"
                        payload = {
                            "chat_id": user_id,
                            "photo": image_url,
                            "caption": text
                        }
                    else:
                        # Send text message
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        payload = {"chat_id": user_id, "text": text}

                    resp = requests.post(url, json=payload, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()

                    if data.get('ok', False):
                        # Create broadcast message document
                        broadcast_doc = User.create_message_document(
                            text=text,
                            role=MessageRole.BROADCAST.value,
                            media_type='image' if image_url else 'text',
                            media_url=image_url
                        )

                        # Store broadcast message in user's history
                        User.add_direct_message(user_id, broadcast_doc, client_username)

                        # Update user status according to business rules
                        if current_status != UserStatus.WAITING.value:
                            User.update_status(user_id, UserStatus.BROADCASTED.value, client_username)

                        successful += 1
                        logger.debug(f"Broadcast message sent to user {user_id}")
                    else:
                        # Message sending failed
                        failed += 1
                        failed_users.append(user_id)

                        # Create failed broadcast message document
                        failed_doc = User.create_message_document(
                            text=f"[FAILED TO SEND] {text}",
                            role=MessageRole.BROADCAST.value,
                            media_type='image' if image_url else 'text',
                            media_url=image_url
                        )

                        # Store failed broadcast attempt
                        User.add_direct_message(user_id, failed_doc, client_username)

                        # Update status to TELEGRAM_FAILED
                        User.update_status(user_id, UserStatus.TELEGRAM_FAILED.value, client_username)

                        error_msg = f"User {user_id}: {data.get('description', 'Unknown error')}"
                        errors.append(error_msg)
                        logger.warning(f"Failed to send broadcast message to {user_id}: {error_msg}")

                except requests.exceptions.Timeout:
                    failed += 1
                    failed_users.append(user.get('user_id'))

                    # Store failed broadcast attempt
                    failed_doc = User.create_message_document(
                        text=f"[TIMEOUT - FAILED TO SEND] {text}",
                        role=MessageRole.BROADCAST.value,
                        media_type='image' if image_url else 'text',
                        media_url=image_url
                    )
                    User.add_direct_message(user_id, failed_doc, client_username)
                    User.update_status(user_id, UserStatus.TELEGRAM_FAILED.value, client_username)

                    error_msg = f"User {user.get('user_id')}: Request timeout"
                    errors.append(error_msg)
                    logger.warning(error_msg)

                except requests.exceptions.RequestException as e:
                    failed += 1
                    failed_users.append(user.get('user_id'))

                    # Store failed broadcast attempt
                    failed_doc = User.create_message_document(
                        text=f"[NETWORK ERROR - FAILED TO SEND] {text}",
                        role=MessageRole.BROADCAST.value,
                        media_type='image' if image_url else 'text',
                        media_url=image_url
                    )
                    User.add_direct_message(user_id, failed_doc, client_username)
                    User.update_status(user_id, UserStatus.TELEGRAM_FAILED.value, client_username)

                    error_msg = f"User {user.get('user_id')}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)

                except Exception as e:
                    failed += 1
                    failed_users.append(user.get('user_id'))

                    # Store failed broadcast attempt
                    failed_doc = User.create_message_document(
                        text=f"[ERROR - FAILED TO SEND] {text}",
                        role=MessageRole.BROADCAST.value,
                        media_type='image' if image_url else 'text',
                        media_url=image_url
                    )
                    User.add_direct_message(user_id, failed_doc, client_username)
                    User.update_status(user_id, UserStatus.TELEGRAM_FAILED.value, client_username)

                    error_msg = f"User {user.get('user_id')}: Unexpected error - {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

                # Implement batching with delay to avoid rate limiting
                if (index + 1) % batch_size == 0 and index + 1 < len(users):
                    logger.info(f"Batch complete. Processed {index + 1}/{len(users)} users. Waiting {delay_between_batches}s...")
                    time.sleep(delay_between_batches)

            # 4. Log completion statistics
            logger.info(f"Broadcast complete for client {client_username}: "
                    f"Total={len(users)}, Successful={successful}, Failed={failed}")

            return {
                'total_users': len(users),
                'successful': successful,
                'failed': failed,
                'failed_users': failed_users,
                'errors': errors if errors else []
            }

        except Exception as e:
            logger.error(f"Unexpected error in broadcast_message: {str(e)}", exc_info=True)
            return {
                'total_users': 0,
                'successful': 0,
                'failed': 0,
                'failed_users': [],
                'errors': [f"Unexpected error: {str(e)}"]
            }

    @staticmethod
    def handle_update(db, update, client_username):
        """Process and handle a Telegram update (message) for a specific client."""
        try:
            from datetime import timedelta

            raw_message = update.get('message') or update.get('edited_message')
            if not raw_message:
                logger.info("Ignoring non-message Telegram update (no message or edited_message field).")
                return True

            text_content = raw_message.get('text', '').strip()
            caption_content = raw_message.get('caption', '').strip()

            if not text_content and not caption_content and not raw_message.get('photo'):
                logger.info("Ignoring Telegram update with no text, caption, or photo content.")
                return True

            from_user = raw_message.get('from', {})
            user_id = str(from_user.get('id')) if from_user.get('id') is not None else None
            if not user_id:
                logger.error("Telegram update missing user id")
                return False

            user_profile_data = {
                'username': from_user.get('username', ''),
                'first_name': from_user.get('first_name'),
                'last_name': from_user.get('last_name'),
                'language_code': from_user.get('language_code'),
                'is_premium': from_user.get('is_premium', False)
            }

            user = User.get_by_id(user_id, client_username)
            should_fetch_photo = True
            CACHE_DURATION = timedelta(hours=24)

            if user and 'profile_photo_last_checked' in user and user.get('profile_photo_last_checked'):
                last_checked = user['profile_photo_last_checked']

                if last_checked.tzinfo is None:
                    last_checked = last_checked.replace(tzinfo=timezone.utc)

                if datetime.now(timezone.utc) - last_checked < CACHE_DURATION:
                    should_fetch_photo = False

            if should_fetch_photo:
                creds = TelegramService.get_client_credentials(client_username)
                token = (creds or {}).get('telegram_access_token')
                if token:
                    photo_url = TelegramService._get_user_profile_photo_url(token, user_id)
                    if photo_url:
                        user_profile_data['profile_photo_url'] = photo_url

                user_profile_data['profile_photo_last_checked'] = datetime.now(timezone.utc)


            text = text_content or caption_content
            timestamp = datetime.fromtimestamp(raw_message.get('date'), timezone.utc)
            messages_to_push = []
            if text.strip() or raw_message.get('photo'):
                message_doc = User.create_message_document(
                    text=text,
                    role=MessageRole.USER.value,
                    timestamp=timestamp,
                    media_type='image' if raw_message.get('photo') else 'text',
                    message_id=raw_message.get('message_id'),
                    entities=raw_message.get('entities'),
                    reply_to_message_id=(raw_message.get('reply_to_message') or {}).get('message_id'),
                    edit_date=datetime.fromtimestamp(raw_message.get('edit_date'), timezone.utc) if raw_message.get('edit_date') else None
                )
                messages_to_push.append(message_doc)


            success = User.upsert_telegram_user_and_messages(
                user_id=user_id,
                client_username=client_username,
                user_profile_data=user_profile_data,
                message_docs=messages_to_push
            )

            if not success:
                logger.warning(f"Failed to store Telegram message via User model: user_id={user_id}, client={client_username}")
                return False

            logger.info(f"Stored Telegram message and updated profile for user {user_id} (client {client_username})")
            return True

        except Exception as e:
            logger.error(f"Unexpected error handling Telegram update: {str(e)}", exc_info=True)
            return False