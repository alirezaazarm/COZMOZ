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
    def handle_update(db, update, client_username):
        """Process and handle a Telegram update (message) for a specific client."""
        try:
            from datetime import timedelta

            message = update.get('message').strip() or update.get('edited_message').strip()
            if not message:
                logger.info("Ignoring non-message Telegram update")
                return True

            from_user = message.get('from', {})
            user_id = str(from_user.get('id')) if from_user.get('id') is not None else None
            if not user_id:
                logger.error("Telegram update missing user id")
                return False

            # --- 1. Caching and Profile Photo Logic ---
            user_profile_data = {
                'username': from_user.get('username', ''),
                'first_name': from_user.get('first_name'),
                'last_name': from_user.get('last_name'),
                'language_code': from_user.get('language_code'),
                'is_premium': from_user.get('is_premium', False)
            }

            # Check if we need to refresh the profile photo
            user = User.get_by_id(user_id, client_username)
            should_fetch_photo = True
            CACHE_DURATION = timedelta(hours=24)

            if user and 'profile_photo_last_checked' in user and user.get('profile_photo_last_checked'):
                last_checked = user['profile_photo_last_checked']

                # --- FIX STARTS HERE ---
                # Ensure the datetime from the database is timezone-aware before comparison
                if last_checked.tzinfo is None:
                    last_checked = last_checked.replace(tzinfo=timezone.utc)
                # --- FIX ENDS HERE ---

                if datetime.now(timezone.utc) - last_checked < CACHE_DURATION:
                    should_fetch_photo = False

            if should_fetch_photo:
                creds = TelegramService.get_client_credentials(client_username)
                token = (creds or {}).get('telegram_access_token')
                if token:
                    photo_url = TelegramService._get_user_profile_photo_url(token, user_id)
                    if photo_url:
                        user_profile_data['profile_photo_url'] = photo_url

                # Always update the checked timestamp, even if fetching failed
                user_profile_data['profile_photo_last_checked'] = datetime.now(timezone.utc)


            # --- 2. Message Processing Logic (remains the same) ---
            # (The existing logic for creating message documents goes here)
            text = message.get('text', '') or ''
            caption = message.get('caption', '') or ''
            timestamp = datetime.fromtimestamp(message.get('date'), timezone.utc)
            # ... and so on for the rest of the message parsing ...
            messages_to_push = []
            if text.strip() or caption.strip() or message.get('photo'):
                # Fleshed out this part based on previous code for a complete example
                message_doc = User.create_message_document(
                    text=text or caption,
                    role=MessageRole.USER.value,
                    timestamp=timestamp,
                    media_type='image' if message.get('photo') else 'text',
                    message_id=message.get('message_id'),
                    entities=message.get('entities'),
                    reply_to_message_id=(message.get('reply_to_message') or {}).get('message_id'),
                    edit_date=datetime.fromtimestamp(message.get('edit_date'), timezone.utc) if message.get('edit_date') else None
                )
                messages_to_push.append(message_doc)


            # --- 3. Call the centralized User model method to save everything ---
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