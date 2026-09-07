import logging
from datetime import datetime, timezone
import requests
from io import BytesIO
from PIL import Image
from ...models.user import User
from ...models.enums import UserStatus, MessageRole, ModuleType, Platform
from ...models.client import Client
from ...utils import helpers
from ..AI.img_search import process_image


logger = logging.getLogger(__name__)

BALE_API_BASE = "https://tapi.bale.ai"


class BaleService:
    @staticmethod
    def _get_file_url(token, file_id):
        """Resolve Bale file_id to a downloadable file URL."""
        try:
            resp = requests.get(
                f"{BALE_API_BASE}/bot{token}/getFile",
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
            return f"{BALE_API_BASE}/file/bot{token}/{file_path}"
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
            logger.error(f"Bale image download failed: {str(e)}")
            return None

    @staticmethod
    def get_client_credentials(client_username):
        """Prefer in-memory credentials; fall back to DB and cache when missing."""
        try:
            creds = helpers.get_client_credentials(client_username)
            # Ensure we actually have Bale token cached; otherwise fetch and cache
            if creds and creds.get('bale_access_token'):
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
            logger.error(f"Failed to get Bale credentials for client {client_username}: {str(e)}")
            return None

    @staticmethod
    def _get_user_profile_photo_url(token, user_id):
        """
        Fetch the user's profile photo URL from Bale.
        Returns the URL of the highest resolution photo, or None.
        Bale API is based on Telegram Bot API, but getUserProfilePhotos may not be supported (404).
        """
        try:
            api_url = f"{BALE_API_BASE}/bot{token}/getUserProfilePhotos"
            params = {"user_id": user_id, "limit": 1}
            resp = requests.get(api_url, params=params, timeout=15)
            if resp.status_code == 404:
                logger.debug(f"Bale getUserProfilePhotos not available for {user_id} (404)")
                return None
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
            return BaleService._get_file_url(token, file_id)

        except requests.exceptions.HTTPError as e:
            # 404 or other HTTP errors should not spam error logs for Bale
            logger.debug(f"Bale getUserProfilePhotos HTTP error for {user_id}: {str(e)}")
            return None
        except Exception as e:
            logger.debug(f"Failed to get user profile photo for {user_id}: {str(e)}")
            return None

    @staticmethod
    def set_webhook(token, webhook_url, secret_token=None):
        """Set Bale webhook URL and optional secret token (mirrors Telegram; Bale docs only show `url` but server accepts `secret_token`)."""
        try:
            payload = {
                "url": webhook_url,
                "drop_pending_updates": False
            }
            if secret_token:
                payload["secret_token"] = secret_token
            resp = requests.post(
                f"{BALE_API_BASE}/bot{token}/setWebhook",
                json=payload,
                timeout=15
            )
            data = resp.json()
            if not data.get("ok"):
                return False, data.get("description", "Failed to set webhook")
            return True, "Webhook configured successfully on Bale"
        except Exception as e:
            logger.error(f"Failed to set Bale webhook: {str(e)}")
            return False, str(e)

    @staticmethod
    def get_webhook_info(token):
        """Query Bale Bot API for current webhook info and bot details."""
        try:
            info_resp = requests.get(f"{BALE_API_BASE}/bot{token}/getWebhookInfo", timeout=15)
            me_resp = requests.get(f"{BALE_API_BASE}/bot{token}/getMe", timeout=15)
            info = info_resp.json().get("result", {}) if info_resp.status_code == 200 else {}
            me = me_resp.json().get("result", {}) if me_resp.status_code == 200 else {}
            return True, {"webhook": info, "bot": me}
        except Exception as e:
            return False, {"error": str(e)}

    @staticmethod
    def send_message(chat_id, text, client_username=None, account_id=None, account_username=None):
        """Send a message to a Bale chat using the token of the exact bot account
        the conversation belongs to (falls back to the client's default token)."""
        try:
            if not client_username:
                logger.error("Bale send_message requires client_username context")
                return None

            token = None
            if account_id:
                client, account = Client.get_client_and_account_by_bale(client_username, account_id=account_id) if hasattr(Client, 'get_client_and_account_by_bale') else (None, None)
                # Fallback generic lookup if Bale-specific helper not available
                if not account:
                    try:
                        fallback_client = Client.get_by_username(client_username)
                        if fallback_client:
                            accounts = fallback_client.get("platforms", {}).get(Platform.BALE.value, {}).get("accounts", [])
                            account = next((acc for acc in accounts if acc.get("id") == account_id), None)
                            client = fallback_client
                    except Exception:
                        pass
                if account and account.get("bale_access_token"):
                    token = account["bale_access_token"]

            if not token and account_username:
                normalized = str(account_username).lstrip("@")
                for acc in Client.get_platform_accounts(client_username, Platform.BALE.value):
                    if (acc.get("username") or acc.get("bot_username")) == normalized:
                        token = acc.get("bale_access_token")
                        break

            if not token:
                creds = BaleService.get_client_credentials(client_username)
                token = creds.get('bale_access_token') if creds else None

            if not token:
                logger.error(f"No Bale token for client: {client_username}")
                return None

            url = f"{BALE_API_BASE}/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            ok = data.get('ok', False)
            if not ok:
                logger.error(f"Bale send failed for client {client_username}: {data}")
                return None
            message_id = data.get('result', {}).get('message_id')
            return message_id
        except Exception as e:
            logger.error(f"Bale send failed: {str(e)}", exc_info=True)
            return None


    @staticmethod
    def broadcast_message(text, client_username, batch_size=50, delay_between_batches=1, image_url=None):
        """
        broadcast message to all Bale users for a specific client.

        This method:
        - Retrieves all Bale users for the given client
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
            logger.info(f"Starting broadcast to all Bale users for client {client_username}")

            # 1. Retrieve all Bale users for this client
            try:
                users = User.get_users_by_platform_for_client(
                    platform="bale",
                    client_username=client_username
                )
            except Exception as e:
                logger.error(f"Failed to retrieve Bale users: {str(e)}")
                return {
                    'total_users': 0,
                    'successful': 0,
                    'failed': 0,
                    'failed_users': [],
                    'errors': [f"Failed to retrieve users: {str(e)}"]
                }

            if not users:
                logger.info(f"No Bale users found for client {client_username}")
                return {
                    'total_users': 0,
                    'successful': 0,
                    'failed': 0,
                    'failed_users': [],
                    'errors': []
                }

            # 2. Resolve global fallback token once; per-user account token is preferred
            global_creds = BaleService.get_client_credentials(client_username)
            global_token = (global_creds or {}).get('bale_access_token')
            if not global_token:
                logger.warning(f"No global Bale token for client {client_username} — will try per-account tokens")

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

                    account_username = (user.get('source') or {}).get('account_username')
                    # Get current user status before sending (scoped to account when possible)
                    current_user = User.get_by_id(user_id, client_username, account_username=account_username)
                    current_status = current_user.get('status') if current_user else UserStatus.WAITING.value

                    # Resolve the exact Bale bot token for this user's account
                    token = None
                    if account_username:
                        normalized = str(account_username).lstrip("@")
                        for acc in Client.get_platform_accounts(client_username, Platform.BALE.value):
                            if (acc.get("username") or acc.get("bot_username")) == normalized:
                                token = acc.get("bale_access_token")
                                break
                    if not token:
                        token = global_token
                    if not token:
                        failed += 1
                        failed_users.append(user_id)
                        err = f"User {user_id}: no Bale token for account @{account_username or 'default'}"
                        errors.append(err)
                        try:
                            failed_doc = User.create_message_document(
                                text=f"[FAILED TO SEND] {text}",
                                role=MessageRole.BROADCAST.value,
                                media_type='image' if image_url else 'text',
                                media_url=image_url
                            )
                            User.add_direct_message(user_id, failed_doc, client_username, account_username=account_username)
                            failed_status = getattr(UserStatus, 'BALE_FAILED', UserStatus.TELEGRAM_FAILED).value
                            User.update_status(user_id, failed_status, client_username, account_username=account_username)
                        except Exception:
                            pass
                        logger.warning(err)
                        continue

                    # Send the message (with or without image)
                    if image_url:
                        # Send photo with caption
                        url = f"{BALE_API_BASE}/bot{token}/sendPhoto"
                        payload = {
                            "chat_id": user_id,
                            "photo": image_url,
                            "caption": text
                        }
                    else:
                        # Send text message
                        url = f"{BALE_API_BASE}/bot{token}/sendMessage"
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

                        # Store broadcast message in user's history (scoped to exact account)
                        User.add_direct_message(user_id, broadcast_doc, client_username, account_username=account_username)

                        # Update user status according to business rules
                        if current_status != UserStatus.WAITING.value:
                            User.update_status(user_id, UserStatus.BROADCASTED.value, client_username, account_username=account_username)

                        successful += 1
                        logger.debug(f"Broadcast message sent to user {user_id} via @{account_username or 'default'}")
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

                        # Store failed broadcast attempt (scoped)
                        User.add_direct_message(user_id, failed_doc, client_username, account_username=account_username)

                        # Update status to BALE_FAILED
                        failed_status = getattr(UserStatus, 'BALE_FAILED', UserStatus.TELEGRAM_FAILED).value
                        User.update_status(user_id, failed_status, client_username, account_username=account_username)

                        error_msg = f"User {user_id}: {data.get('description', 'Unknown error')}"
                        errors.append(error_msg)
                        logger.warning(f"Failed to send broadcast message to {user_id}: {error_msg}")

                except requests.exceptions.Timeout:
                    failed += 1
                    failed_users.append(user.get('user_id'))

                    # Store failed broadcast attempt (scoped)
                    failed_doc = User.create_message_document(
                        text=f"[TIMEOUT - FAILED TO SEND] {text}",
                        role=MessageRole.BROADCAST.value,
                        media_type='image' if image_url else 'text',
                        media_url=image_url
                    )
                    User.add_direct_message(user_id, failed_doc, client_username, account_username=account_username)
                    failed_status = getattr(UserStatus, 'BALE_FAILED', UserStatus.TELEGRAM_FAILED).value
                    User.update_status(user_id, failed_status, client_username, account_username=account_username)

                    error_msg = f"User {user.get('user_id')}: Request timeout"
                    errors.append(error_msg)
                    logger.warning(error_msg)

                except requests.exceptions.RequestException as e:
                    failed += 1
                    failed_users.append(user.get('user_id'))

                    # Store failed broadcast attempt (scoped)
                    failed_doc = User.create_message_document(
                        text=f"[NETWORK ERROR - FAILED TO SEND] {text}",
                        role=MessageRole.BROADCAST.value,
                        media_type='image' if image_url else 'text',
                        media_url=image_url
                    )
                    User.add_direct_message(user_id, failed_doc, client_username, account_username=account_username)
                    failed_status = getattr(UserStatus, 'BALE_FAILED', UserStatus.TELEGRAM_FAILED).value
                    User.update_status(user_id, failed_status, client_username, account_username=account_username)

                    error_msg = f"User {user.get('user_id')}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)

                except Exception as e:
                    failed += 1
                    failed_users.append(user.get('user_id'))

                    # Store failed broadcast attempt (scoped)
                    failed_doc = User.create_message_document(
                        text=f"[ERROR - FAILED TO SEND] {text}",
                        role=MessageRole.BROADCAST.value,
                        media_type='image' if image_url else 'text',
                        media_url=image_url
                    )
                    User.add_direct_message(user_id, failed_doc, client_username, account_username=account_username)
                    failed_status = getattr(UserStatus, 'BALE_FAILED', UserStatus.TELEGRAM_FAILED).value
                    User.update_status(user_id, failed_status, client_username, account_username=account_username)

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
    def handle_update(db, update, client_username, account_username=None):
        """Process and handle a Bale update (message) for a specific client."""
        if not account_username:
            try:
                accts = Client.get_platform_accounts(client_username, Platform.BALE.value)
                if accts:
                    first = accts[0]
                    account_username = first.get("username") or first.get("bot_username") or first.get("id")
            except Exception:
                pass
        if not account_username:
            logger.error(f"Bale handle_update missing account_username for client {client_username} - cannot create user without source.account_username")
            return False
        try:
            from datetime import timedelta

            raw_message = update.get('message') or update.get('edited_message')
            if not raw_message:
                logger.info("Ignoring non-message Bale update (no message or edited_message field).")
                return True

            text_content = raw_message.get('text', '').strip()
            caption_content = raw_message.get('caption', '').strip()

            if not text_content and not caption_content and not raw_message.get('photo'):
                logger.info("Ignoring Bale update with no text, caption, or photo content.")
                return True

            from_user = raw_message.get('from', {})
            user_id = str(from_user.get('id')) if from_user.get('id') is not None else None
            if not user_id:
                logger.error("Bale update missing user id")
                return False

            user_profile_data = {
                'username': from_user.get('username', ''),
                'first_name': from_user.get('first_name'),
                'last_name': from_user.get('last_name'),
                'language_code': from_user.get('language_code'),
                'is_premium': from_user.get('is_premium', False)
            }

            user = User.get_by_id(user_id, client_username, account_username=account_username)
            should_fetch_photo = True
            CACHE_DURATION = timedelta(hours=24)

            if user and 'profile_photo_last_checked' in user and user.get('profile_photo_last_checked'):
                last_checked = user['profile_photo_last_checked']

                if last_checked.tzinfo is None:
                    last_checked = last_checked.replace(tzinfo=timezone.utc)

                if datetime.now(timezone.utc) - last_checked < CACHE_DURATION:
                    should_fetch_photo = False

            if should_fetch_photo:
                creds = BaleService.get_client_credentials(client_username)
                token = (creds or {}).get('bale_access_token')
                if token:
                    photo_url = BaleService._get_user_profile_photo_url(token, user_id)
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

            # Try Bale-specific upsert if available, otherwise generic upsert logic for Bale platform
            if hasattr(User, 'upsert_bale_user_and_messages'):
                success = User.upsert_bale_user_and_messages(
                    user_id=user_id,
                    client_username=client_username,
                    user_profile_data=user_profile_data,
                    message_docs=messages_to_push,
                    account_username=account_username
                )
            else:
                # Generic upsert for Bale (mirrors telegram logic but with platform='bale')
                try:
                    from ...models.database import USERS_COLLECTION
                    set_spec = {
                        "status": UserStatus.WAITING.value,
                        "updated_at": datetime.now(timezone.utc),
                        **user_profile_data
                    }
                    user_doc_on_insert = User.create_user_document(
                        user_id=user_id,
                        username=user_profile_data.get('username', ''),
                        client_username=client_username,
                        status=UserStatus.WAITING.value,
                        platform=Platform.BALE.value,
                        account_username=account_username,
                        first_name=user_profile_data.get('first_name'),
                        last_name=user_profile_data.get('last_name'),
                        language_code=user_profile_data.get('language_code'),
                        is_premium=user_profile_data.get('is_premium', False),
                        profile_photo_url=user_profile_data.get('profile_photo_url')
                    )
                    for key in list(set_spec.keys()):
                        user_doc_on_insert.pop(key, None)
                    user_doc_on_insert.pop("direct_messages", None)
                    user_doc_on_insert.pop("comments", None)
                    user_doc_on_insert.pop("reactions", None)
                    update_query = {
                        "$setOnInsert": user_doc_on_insert,
                        "$set": set_spec
                    }
                    if messages_to_push:
                        update_query["$push"] = {"direct_messages": {"$each": messages_to_push}}
                    identity = {
                        "user_id": user_id,
                        "source.client_username": client_username,
                        "source.account_username": account_username or None,
                    }
                    # Use same scoping as telegram (account_username aware)
                    result = db[USERS_COLLECTION].update_one(
                        User._apply_account(identity, account_username),
                        update_query,
                        upsert=True
                    )
                    success = result.modified_count > 0 or result.upserted_id is not None or result.matched_count > 0
                except Exception as e:
                    logger.error(f"Failed to upsert Bale user (generic path): {str(e)}", exc_info=True)
                    success = False

            if not success:
                logger.warning(f"Failed to store Bale message via User model: user_id={user_id}, client={client_username}")
                return False

            logger.info(f"Stored Bale message and updated profile for user {user_id} (client {client_username})")
            return True

        except Exception as e:
            logger.error(f"Unexpected error handling Bale update: {str(e)}", exc_info=True)
            return False
