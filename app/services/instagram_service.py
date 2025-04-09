# -*- coding: utf-8 -*-
import requests
from ..config import Config
import logging
import re
from datetime import datetime, timezone
from PIL import Image
from io import BytesIO
from ..models.user import User
from ..models.enums import UserStatus, MessageRole
from ..models.post import Post
from ..models.story import Story

logger = logging.getLogger(__name__)

# Global variables for fixed responses
COMMENT_FIXED_RESPONSES = {}
DIRECT_FIXED_RESPONSES = {}
# Global variable for app settings
APP_SETTINGS = {}

def parse_instagram_timestamp(ts):
    if not ts:
        return datetime.now(timezone.utc)

    # If the timestamp is numeric, assume it's a Unix timestamp
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, timezone.utc)
        except Exception as e:
            logger.warning(f"Error parsing numeric timestamp '{ts}': {str(e)}; using now()")
            return datetime.now(timezone.utc)

    try:
        ts_str = str(ts)
        cleaned_str = ts_str.replace('Z', '+00:00')
        if '+0000' in cleaned_str:
            cleaned_str = cleaned_str.replace('+0000', '+00:00')
        if '+' not in cleaned_str and 'T' in cleaned_str:
            cleaned_str += '+00:00'
        return datetime.fromisoformat(cleaned_str)
    except ValueError as ve:
        logger.warning(f"Unable to parse timestamp '{ts}' - {str(ve)}; using now() instead")
        return datetime.now(timezone.utc)

class InstagramService:
    @staticmethod
    def send_message(recipient_id, text):
        link_pattern = re.compile(r'https?://\S+')
        links = link_pattern.findall(text)
        if links:
            logger.info(f"Found {len(links)} links in message, using split message function")
            return InstagramService.send_split_messages(recipient_id, text)

        try:
            logger.info(f"Sending single message to {recipient_id}")
            response = requests.post(
                "https://graph.instagram.com/v21.0/me/messages",
                headers={"Authorization": f"Bearer {Config.PAGE_ACCESS_TOKEN}"},
                json={"recipient": {"id": recipient_id}, "message": {"text": text}},
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Message sent successfully to {recipient_id}")
            return True
        except Exception as e:
            logger.error(f"Instagram send failed: {str(e)}")
            return False

    @staticmethod
    def send_split_messages(user_id, text):
        """Split a long message into multiple messages, preserving sentence integrity and links"""
        try:
            # Set a conservative character limit for Instagram
            MAX_CHAR_LIMIT = 950  # Reduced from 1500 to 950 based on API errors

            logger.info(f"Splitting message of length {len(text)} for user {user_id}")

            # If message is short enough, just send it directly
            if len(text) <= MAX_CHAR_LIMIT:
                return InstagramService.send_message_simple(user_id, text)

            # Handle markdown links - convert them to plain text
            # Markdown pattern: [text](url)
            try:
                markdown_pattern = re.compile(r'\[(.*?)\]\((https?://[^\s)]+)\)')
                # Replace markdown links with just the URL
                text = markdown_pattern.sub(r'\1: \2', text)
            except Exception as e:
                logger.error(f"Error processing markdown links: {e}")
                # Continue without markdown processing if it fails

            # Find URL pattern to avoid splitting in the middle of URLs
            url_pattern = re.compile(r'https?://[^\s]+')
            urls = url_pattern.findall(text)

            # Log found URLs for debugging
            if urls:
                logger.info(f"Found {len(urls)} URLs in message: {urls[:3]}...")

            # Split by different section markers common in product listings
            # This works better for product listings than splitting by sentences
            section_markers = [
                '\n\n',  # Double line break often separates products
                '\n',    # Single line break separates product details
                '. ',    # Period followed by space for sentences
                '\u060C ',  # Persian comma (،)
                '\u061B ',  # Persian semicolon (؛)
                '! ',    # Exclamation
                '? ',    # Question mark
                '\u061F '  # Persian question mark (؟)
            ]

            # Special marker for products in numbered lists
            numbered_list_pattern = re.compile(r'\n\d+\.\s+')
            products = numbered_list_pattern.split(text)

            # If we have clear product sections (numbered list items), use those
            if len(products) > 1:
                logger.info(f"Found {len(products)} numbered product sections")
                messages = []
                current_message = products[0]  # First part before any numbers

                for i, product in enumerate(products[1:], 1):
                    product_text = f"\n{i}. {product}"

                    # Check if adding this product would exceed the limit
                    if len(current_message) + len(product_text) <= MAX_CHAR_LIMIT:
                        current_message += product_text
                    else:
                        # Add current message to list and start a new one
                        if current_message.strip():
                            messages.append(current_message.strip())
                        current_message = product_text

                # Add the last message if there's anything left
                if current_message.strip():
                    messages.append(current_message.strip())

                logger.info(f"Split message into {len(messages)} parts based on product sections")
            else:
                # Fall back to regular splitting
                messages = []
                remaining_text = text
                current_message = ""

                # First try to split by double newlines (product sections)
                logger.debug("Attempting to split by section markers")
                while remaining_text:
                    # Find the next best split point
                    best_split_point = -1
                    best_split_marker = ""

                    for marker in section_markers:
                        # Look for the marker within the limit
                        search_limit = MAX_CHAR_LIMIT - len(current_message)
                        if search_limit <= 0:
                            # Current message is already at the limit
                            break

                        pos = remaining_text[:search_limit].find(marker)

                        # If found and better than current best
                        if pos >= 0 and (best_split_point == -1 or pos > best_split_point):
                            best_split_point = pos
                            best_split_marker = marker

                    # If we found a good split point
                    if best_split_point >= 0:
                        split_pos = best_split_point + len(best_split_marker)
                        chunk = remaining_text[:split_pos]

                        # Check if adding this chunk would exceed the limit
                        if len(current_message) + len(chunk) <= MAX_CHAR_LIMIT:
                            current_message += chunk
                            remaining_text = remaining_text[split_pos:]
                        else:
                            # Current message is full, store it and start a new one
                            if current_message:
                                messages.append(current_message)
                            current_message = chunk
                            remaining_text = remaining_text[split_pos:]
                    else:
                        # No good split point found, force split at the limit
                        available_space = MAX_CHAR_LIMIT - len(current_message)

                        if available_space > 0:
                            # Add as much as possible to current message
                            chunk = remaining_text[:available_space]
                            current_message += chunk
                            remaining_text = remaining_text[available_space:]

                        # Store current message
                        if current_message:
                            messages.append(current_message)
                        current_message = ""

                        # If remaining text is still too long, start a new message
                        if len(remaining_text) > 0:
                            if len(remaining_text) <= MAX_CHAR_LIMIT:
                                messages.append(remaining_text)
                                remaining_text = ""
                            else:
                                # We'll process the rest in the next iteration
                                continue

                # Add final message if there's anything left
                if current_message:
                    messages.append(current_message)

            # Log the splitting results
            logger.info(f"Split message into {len(messages)} parts")
            for i, msg in enumerate(messages):
                logger.debug(f"Message part {i+1}/{len(messages)}: {len(msg)} chars")
                if len(msg) > MAX_CHAR_LIMIT:
                    logger.warning(f"Message part {i+1} exceeds limit: {len(msg)} chars, truncating")
                    messages[i] = msg[:900] + "..."

            # Send each message
            success = True
            for i, message in enumerate(messages):
                logger.info(f"Sending message part {i+1}/{len(messages)} ({len(message)} chars)")

                # If this part is empty somehow, skip it
                if not message.strip():
                    logger.warning(f"Skipping empty message part {i+1}")
                    continue

                # Send this part without part numbers as requested
                part_success = InstagramService.send_message_simple(user_id, message)

                if part_success:
                    logger.info(f"Successfully sent part {i+1}/{len(messages)}")
                else:
                    logger.error(f"Failed to send part {i+1}/{len(messages)}")

                success = success and part_success

                # Add a larger delay between messages to avoid rate limiting
                if i < len(messages)-1:
                    import time
                    time.sleep(2.0)  # Increased from 0.5 to 2.0 seconds

            return success
        except Exception as e:
            logger.error(f"Failed to split and send message: {str(e)}", exc_info=True)
            # Try the original message as a fallback, truncated if necessary
            try:
                # Try to handle markdown links first
                truncated_text = text
                try:
                    markdown_pattern = re.compile(r'\[(.*?)\]\((https?://[^\s)]+)\)')
                    truncated_text = markdown_pattern.sub(r'\1: \2', text)
                except Exception as md_error:
                    logger.error(f"Error processing markdown links in fallback: {md_error}")
                    # Continue with original text if markdown processing fails

                truncated = truncated_text[:900] + "..." if len(truncated_text) > 900 else truncated_text
                logger.info(f"Attempting to send truncated message ({len(truncated)} chars) as fallback")
                return InstagramService.send_message_simple(user_id, truncated)
            except Exception as fallback_error:
                logger.error(f"Fallback sending also failed: {str(fallback_error)}")
                return False

    @staticmethod
    def send_message_simple(user_id, text):
        """Send a simple message without any splitting logic"""
        MAX_RETRIES = 2
        RETRY_DELAY = 2  # seconds - increased from 1 to 2 seconds

        try:
            # Ensure text doesn't exceed Instagram's limits
            if len(text) > 1000:
                logger.warning(f"Message too long ({len(text)} chars), will be truncated")
                text = text[:980] + "..."

            # Try to make the API call with retries
            for attempt in range(MAX_RETRIES + 1):
                try:
                    logger.info(f"Sending message to {user_id} (attempt {attempt+1}/{MAX_RETRIES+1})")
                    response = requests.post(
                        "https://graph.instagram.com/v21.0/me/messages",
                        headers={"Authorization": f"Bearer {Config.PAGE_ACCESS_TOKEN}"},
                        json={"recipient": {"id": user_id}, "message": {"text": text}},
                        timeout=30  # Increased from 15 to 30 seconds
                    )

                    # Log the response details
                    logger.debug(f"Instagram API response: status={response.status_code}, content={response.text[:100]}...")

                    # Check for success
                    response.raise_for_status()
                    logger.info(f"Message sent successfully to {user_id}")
                    return True

                except requests.exceptions.HTTPError as http_err:
                    error_message = f"HTTP error: {http_err}"
                    error_response = getattr(http_err, 'response', None)
                    status_code = getattr(error_response, 'status_code', None)
                    response_text = getattr(error_response, 'text', None)

                    # Log detailed error information
                    logger.error(f"Instagram API error (attempt {attempt+1}): status={status_code}, response={response_text}")

                    # Check if this is a rate limiting issue (429) or server error (5xx)
                    if status_code in [429, 500, 502, 503, 504] and attempt < MAX_RETRIES:
                        retry_delay = RETRY_DELAY * (attempt + 1)  # Exponential backoff
                        logger.info(f"Retrying in {retry_delay} seconds (attempt {attempt+1}/{MAX_RETRIES})")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(f"Instagram API error (non-retriable or max retries reached): {error_message}")
                        return False

                except requests.exceptions.ConnectionError as conn_err:
                    logger.error(f"Connection error (attempt {attempt+1}): {str(conn_err)}")
                    if attempt < MAX_RETRIES:
                        retry_delay = RETRY_DELAY * (attempt + 1)
                        logger.info(f"Retrying in {retry_delay} seconds")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error("Max retries reached for connection error")
                        return False

                except requests.exceptions.Timeout as timeout_err:
                    logger.error(f"Timeout error (attempt {attempt+1}): {str(timeout_err)}")
                    if attempt < MAX_RETRIES:
                        retry_delay = RETRY_DELAY * (attempt + 1)
                        logger.info(f"Retrying in {retry_delay} seconds")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error("Max retries reached for timeout error")
                        return False

            # If we get here, all retries failed
            logger.error(f"Failed to send message after {MAX_RETRIES+1} attempts")
            return False

        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_comment_reply(comment_id, text):
        try:
            url = f"https://graph.instagram.com/v21.0/{comment_id}/replies"
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {Config.PAGE_ACCESS_TOKEN}"},
                json={"message": text},
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send comment reply: {str(e)}")
            return False

    @staticmethod
    def check_content_type(url):
        """Check the content type of a URL"""
        try:
            response = requests.head(url, allow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get('content-type').lower()

            if 'image' in content_type:
                return "image"
            elif 'audio' in content_type:
                return "audio"
            elif 'video' in content_type:
                return "video"
            else:
                return "unknown"

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching URL content type: {str(e)}")
            return "unknown"

    @staticmethod
    def download_image(url):
        """Download an image from a URL"""
        try:
            if not url:
                raise ValueError("No URL provided")
            response = requests.get(
                url,
                stream=True,
                headers={"Authorization": f"Bearer {Config.PAGE_ACCESS_TOKEN}"},
                timeout=15
            )
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))
            return image
        except Exception as e:
            logger.error(f"Image download failed: {str(e)}")
            return None

    @staticmethod
    def process_user(user_data):
        try:
            user_id = user_data['id']
            logger.debug(f"[process_user] Processing user: {user_id}, data: {user_data}")

            recipient_type = user_data.get('type', '')
            if 'recipient' in recipient_type:
                logger.debug(f"[process_user] Skipping recipient user (ID: {user_id})")
                return None

            user = User.get_by_id(user_id)
            logger.debug(f"[process_user] User lookup result: {user is not None}")

            if not user:
                username = user_data.get('username')

                logger.info(f"[process_user] Creating user {user_id} with username: {username}")

                user_doc = User.create( user_id=user_id,  username=username, status=UserStatus.SCRAPED.value,  )

                if user_doc:
                    logger.debug(f"[process_user] Created user: {user_doc['user_id']}")
                    return user_doc
                logger.error(f"[process_user] Failed to create user {user_id}")
                return None

            logger.debug(f"[process_user] Found existing user: {user_id}")
            return user

        except KeyError as ke:
            logger.error(f"[process_user] Invalid user data: Missing {str(ke)}")
            raise
        except Exception as e:
            logger.error(f"[process_user] User processing error: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def update_comment_status(db, user_id, comment_id, status):
        """Update the status of a comment in the database"""
        try:
            # Update the status of the comment in the user's comments array
            result = db.users.update_one(
                {"user_id": user_id, "comments.comment_id": comment_id},
                {"$set": {"comments.$.status": status}}
            )

            if result.modified_count > 0:
                logger.info(f"Updated status of comment {comment_id} to {status}")
                return True
            else:
                logger.warning(f"Comment {comment_id} not found for user {user_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to update comment status: {str(e)}")
            return False

    @staticmethod
    def set_app_settings(settings):
        """Set app settings from external module"""
        global APP_SETTINGS

        # Log the current settings
        logger.info(f"InstagramService - Current APP_SETTINGS: {APP_SETTINGS}")

        # Store the new settings
        APP_SETTINGS = settings

        # Log the new settings
        logger.info(f"InstagramService - New APP_SETTINGS: {APP_SETTINGS}")

        # Explicitly log the assistant status to verify
        assistant_enabled = APP_SETTINGS.get('assistant', True)
        logger.info(f"InstagramService - Assistant is now {'ENABLED' if assistant_enabled else 'DISABLED'}")

        return True

    @staticmethod
    def set_fixed_responses(response_type, responses):
        """Set fixed responses from external module"""
        if response_type == 'Comment':
            global COMMENT_FIXED_RESPONSES
            COMMENT_FIXED_RESPONSES = responses
            logger.info(f"Comment fixed responses set in InstagramService with {len(responses)} entries")
        elif response_type == 'Direct':
            global DIRECT_FIXED_RESPONSES
            DIRECT_FIXED_RESPONSES = responses
            logger.info(f"Direct fixed responses set in InstagramService with {len(responses)} entries")
        return True

    @staticmethod
    def handle_message(db, message_data):
        """Process and handle an Instagram direct message"""
        try:
            # Log the message data for debugging
            logger.debug(f"[handle_message] Received message data: {message_data}")

            required_fields = ['id', 'from', 'timestamp']
            for field in required_fields:
                if field not in message_data:
                    logger.error(f"[handle_message] Missing required field: {field}")
                    return False

            sender_info = message_data['from']
            user_id = sender_info.get('id')

            if not user_id:
                logger.error("[handle_message] Missing user ID in from data")
                return False

            # Get message details
            message_text = message_data.get('text', '')
            media_type = message_data.get('media_type')
            media_url = message_data.get('media_url')
            timestamp = message_data.get('timestamp')
            is_echo = message_data.get('is_echo', False)
            role = message_data.get('role', MessageRole.USER.value)

            logger.info(f"[handle_message] Processing message ID: {message_data.get('id')} from user: {user_id}, is_echo: {is_echo}, role: {role}")

            # Skip if message has no content (no text AND no media)
            if not message_text and not media_url:
                logger.warning(f"[handle_message] Skipping empty message from user {user_id}")
                return False

            # *** SPECIAL HANDLING FOR ECHO MESSAGES FROM BUSINESS ACCOUNT ***
            # For echo messages from the business account, we need to find or create the actual user
            actual_user_id = user_id
            if is_echo and user_id == Config.PAGE_ID:
                logger.debug(f"[handle_message] This is an echo message from our business account.")
                # We need to find the appropriate user record

                # For messages, the recipient ID is the actual user
                if 'recipient' in message_data:
                    actual_user_id = message_data.get('recipient', {}).get('id')
                    logger.debug(f"[handle_message] Found recipient ID in message_data: {actual_user_id}")

                if not actual_user_id or actual_user_id == Config.PAGE_ID:
                    logger.error(f"[handle_message] Could not determine actual user ID for echo message. Using default: {user_id}")
                    actual_user_id = user_id
                else:
                    logger.debug(f"[handle_message] Using recipient ID as actual user: {actual_user_id}")
                    # Make sure the user exists
                    user_check = db.users.find_one({"user_id": actual_user_id})
                    if not user_check:
                        logger.info(f"[handle_message] Creating user record for recipient: {actual_user_id}")
                        user_doc = User.create_user_document(
                            user_id=actual_user_id
                        )
                        db.users.insert_one(user_doc)
                        logger.info(f"[handle_message] Created new user record for recipient ID: {actual_user_id}")
                    else:
                        logger.debug(f"[handle_message] Found existing user record for recipient ID: {actual_user_id}")

            # Process the sender user, this creates a document if needed
            if not is_echo or user_id != Config.PAGE_ID:
                # Only process the sender user if it's not an echo from business account
                user = InstagramService.process_user(sender_info)
                if not user:
                    logger.error(f"[handle_message] Failed to process user: {user_id}")
                    return False

            # Check for fixed responses if there's text content
            if message_text and "DIRECT_FIXED_RESPONSES" in globals() and DIRECT_FIXED_RESPONSES.get(message_text):
                fixed_response = DIRECT_FIXED_RESPONSES.get(message_text)
                logger.info(f"[handle_message] Found fixed response for message: {message_text}")

                success = InstagramService.send_message(actual_user_id, fixed_response['DM'])
                if success:
                    logger.info("[handle_message] Fixed response sent successfully")
                else:
                    logger.error("[handle_message] Failed to send fixed response")

            # Handle echo messages (admin or assistant replies)
            if is_echo:
                # Determine the correct role based on assistant setting
                is_assistant_enabled = "APP_SETTINGS" in globals() and APP_SETTINGS.get('assistant', True)
                msg_role = MessageRole.ASSISTANT.value if is_assistant_enabled else MessageRole.ADMIN.value
                logger.debug(f"[handle_message] Echo message with role: {msg_role}, assistant enabled: {is_assistant_enabled}")

                # Create a message document
                message_doc = User.create_message_document(
                    text=message_text,
                    role=msg_role,
                    media_type=media_type,
                    media_url=media_url,
                    timestamp=timestamp
                )

                logger.debug(f"[handle_message] Created message document for echo message: {message_doc}")

                # Always update status to REPLIED for echo messages
                try:
                    result = db.users.update_one(
                        {"user_id": actual_user_id},  # Use the actual user ID
                        {
                            "$push": {"direct_messages": message_doc},
                            "$set": {"status": UserStatus.REPLIED.value, "updated_at": datetime.now(timezone.utc)}
                        }
                    )

                    logger.debug(f"[handle_message] DB update result for echo message: matched={result.matched_count}, modified={result.modified_count}")

                    if result.modified_count > 0:
                        logger.info(f"[handle_message] Successfully stored echo message {message_data.get('id')} for user {actual_user_id} with role {msg_role} and status REPLIED")
                    else:
                        logger.warning(f"[handle_message] Failed to update user document for echo message {message_data.get('id')} from user {actual_user_id}")
                        # Check if user exists
                        user_check = db.users.find_one({"user_id": actual_user_id})
                        if not user_check:
                            logger.error(f"[handle_message] User {actual_user_id} not found in database!")

                            # Create the user since they don't exist
                            logger.info(f"[handle_message] Creating missing user record for recipient: {actual_user_id}")
                            user_doc = User.create_user_document(
                                user_id=actual_user_id
                            )
                            db.users.insert_one(user_doc)
                            logger.info(f"[handle_message] Created user, now adding the message")

                            # Try the update again
                            result = db.users.update_one(
                                {"user_id": actual_user_id},
                                {
                                    "$push": {"direct_messages": message_doc},
                                    "$set": {"status": UserStatus.REPLIED.value, "updated_at": datetime.now(timezone.utc)}
                                }
                            )
                            logger.info(f"[handle_message] Second attempt result: matched={result.matched_count}, modified={result.modified_count}")
                        else:
                            logger.debug(f"[handle_message] User {actual_user_id} exists in database")

                            # Try an upsert operation as a last resort
                            try:
                                result = db.users.update_one(
                                    {"user_id": actual_user_id},
                                    {
                                        "$push": {"direct_messages": message_doc},
                                        "$set": {"status": UserStatus.REPLIED.value, "updated_at": datetime.now(timezone.utc)}
                                    },
                                    upsert=True
                                )
                                logger.info(f"[handle_message] Upsert attempt: matched={result.matched_count}, modified={result.modified_count}, upserted_id={result.upserted_id}")
                            except Exception as upsert_error:
                                logger.error(f"[handle_message] Upsert operation failed: {str(upsert_error)}")
                except Exception as db_error:
                    logger.error(f"[handle_message] Database error while storing echo message: {str(db_error)}", exc_info=True)
                    return False

                return True

            # Handle regular user messages
            # Create a user message document
            message_doc = User.create_message_document(
                text=message_text,
                role=MessageRole.USER.value,
                media_type=media_type,
                media_url=media_url,
                timestamp=timestamp
            )

            # Check if assistant is enabled in app settings
            is_assistant_enabled = "APP_SETTINGS" in globals() and APP_SETTINGS.get('assistant', True)

            # Store message in database with appropriate status
            try:
                result = db.users.update_one(
                    {"user_id": actual_user_id},  # Use the actual user ID
                    {
                        "$push": {"direct_messages": message_doc},
                        "$set": {"status": UserStatus.WAITING.value, "updated_at": datetime.now(timezone.utc)}
                    }
                )

                logger.debug(f"[handle_message] DB update result for user message: matched={result.matched_count}, modified={result.modified_count}")

                if result.modified_count == 0:
                    logger.warning(f"[handle_message] Failed to update user document for user message from {actual_user_id}")

            except Exception as db_error:
                logger.error(f"[handle_message] Database error while storing user message: {str(db_error)}", exc_info=True)
                return False

            if is_assistant_enabled:
                logger.info(f"[handle_message] Assistant is enabled - Message {message_data.get('id')} stored for user {actual_user_id} with WAITING status for OpenAI processing")
            else:
                logger.info(f"[handle_message] Assistant is disabled - Message {message_data.get('id')} stored for user {actual_user_id} with WAITING status for admin reply")

            return True

        except Exception as e:
            logger.error(f"[handle_message] Unexpected error in handle_message: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def handle_comment(db, comment_data):
        """Process and handle an Instagram comment"""
        try:
            logger.info(f"Processing comment ID: {comment_data.get('comment_id')}")
            required_fields = ['comment_id', 'post_id', 'user_id', 'comment_text', 'timestamp']
            for field in required_fields:
                if field not in comment_data:
                    raise ValueError(f"Missing required field: {field}")

            # Parse timestamp using helper function
            timestamp = parse_instagram_timestamp(comment_data.get('timestamp'))

            # For backward compatibility, also check created_time if timestamp parsing failed
            if timestamp == datetime.now(timezone.utc) and comment_data.get('created_time'):
                try:
                    timestamp = datetime.fromtimestamp(comment_data.get('created_time'), timezone.utc)
                except Exception as e:
                    logger.error(f"Failed to parse created_time for comment {comment_data['comment_id']}: {str(e)}")

            user_info = {
                'id': comment_data['user_id'],
                'username': comment_data.get('username')
            }

            # Process the user who made the comment
            user = InstagramService.process_user(user_info)
            if not user:
                logger.error(f"Failed to process user: {user_info['id']}")
                return False

            # In MongoDB, user is always a dictionary
            user_id = user.get('user_id')
            if not user_id:
                logger.error(f"User document is missing user_id field: {user}")
                return False

            # Get the comment text for fixed response matching
            comment_text = comment_data['comment_text']

            # Create comment document
            comment_doc = User.create_comment_document(
                post_id=comment_data['post_id'],
                comment_id=comment_data['comment_id'],
                text=comment_text,
                parent_id=comment_data.get('parent_id'),
                timestamp=timestamp
            )

            # Add status field to comment document
            comment_doc['status'] = 'pending'

            # Add comment to user's comments array
            result = db.users.update_one(
                {"user_id": user_id},
                {"$push": {"comments": comment_doc}}
            )

            if result.modified_count == 0:
                logger.error(f"Failed to add comment to user {user_id}")
                return False

            logger.info(f"Added comment {comment_data['comment_id']} to user {user_id}")

            # Initialize reply flags
            replied_in_comment = False
            replied_in_direct = False

            # Check if the comment triggers a fixed response
            if "COMMENT_FIXED_RESPONSES" in globals() and COMMENT_FIXED_RESPONSES.get(comment_text):
                fixed_response = COMMENT_FIXED_RESPONSES.get(comment_text)
                logger.info(f"Found fixed response for comment: {comment_text}")

                # Send reply as a comment if available
                if fixed_response.get('comment'):
                    comment_reply = fixed_response['comment']
                    comment_success = InstagramService.send_comment_reply(comment_data['comment_id'], comment_reply)
                    if comment_success:
                        logger.info(f"Sent fixed comment reply to comment {comment_data['comment_id']}")
                        replied_in_comment = True
                    else:
                        logger.error(f"Failed to send fixed comment reply to comment {comment_data['comment_id']}")

                # Send reply as a direct message if available
                if fixed_response.get('DM'):
                    dm_reply = fixed_response['DM']
                    dm_success = InstagramService.send_message(user_id, dm_reply)
                    if dm_success:
                        logger.info(f"Sent fixed DM reply to user {user_id} for comment {comment_data['comment_id']}")
                        replied_in_direct = True
                    else:
                        logger.error(f"Failed to send fixed DM reply to user {user_id}")

            # Update the comment status based on replies
            if replied_in_direct and replied_in_comment:
                InstagramService.update_comment_status(db, user_id, comment_doc['comment_id'], "replied_in_cm_DM")
            elif replied_in_direct:
                InstagramService.update_comment_status(db, user_id, comment_doc['comment_id'], "replied_in_DM")
            elif replied_in_comment:
                InstagramService.update_comment_status(db, user_id, comment_doc['comment_id'], "replied_in_cm")
            else:
                InstagramService.update_comment_status(db, user_id, comment_doc['comment_id'], "pending")

            return True

        except ValueError as ve:
            logger.error(f"Invalid comment data: {str(ve)}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error in handle_comment: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def get_posts():
        """
        Retrieves posts from the IG endpoint and stores them in MongoDB using model classes.
        Also extracts comments and their replies, storing them in each commenter's user document.
        """
        try:
            base_endpoint = f"https://graph.facebook.com/v22.0/{Config.PAGE_ID}"
            post_endpoint = "/media?fields=caption,media_url,media_type,id,like_count,timestamp,comments.limit(1000){id,timestamp,text,from,like_count,replies.limit(1000){id,timestamp,text,from,like_count}}&limit=1000"
            params = {"access_token": Config.FB_ACCESS_TOKEN}
            response = requests.get(base_endpoint + post_endpoint, params=params)
            response.raise_for_status()

            data = response.json()
            posts = data.get('data', [])

            for post in posts:
                # Create/update post using Post model
                post_data = {
                    "id": post.get('id'),
                    "caption": post.get('caption', ''),
                    "media_url": post.get('media_url', ''),
                    "media_type": post.get('media_type', ''),
                    "like_count": post.get('like_count', 0),
                    "timestamp": post.get('timestamp')
                }
                Post.create_or_update_from_instagram(post_data)

                # Process comments
                comment_data = post.get('comments', {}).get('data', [])
                for comment in comment_data:
                    from_user = comment.get('from', {})
                    from_user_id = from_user.get('id')
                    from_username = from_user.get('username', '')

                    if from_user_id:
                        # Process commenter using User model
                        commenter_info = {
                            "id": from_user_id,
                            "username": from_username
                        }
                        commented_user = InstagramService.process_user(commenter_info)

                        if commented_user:
                            # Create top-level comment using User model's method
                            comment_doc = User.create_comment_document(
                                post_id=post.get('id'),
                                comment_id=comment.get('id'),
                                text=comment.get('text', ''),
                                parent_id=None,
                                timestamp=parse_instagram_timestamp(comment.get('timestamp')),
                                status="pending"
                            )
                            comment_doc["like_count"] = comment.get('like_count', 0)

                            # Add comment to user's comments array
                            User.add_comment_to_user(from_user_id, comment_doc)

                            # Process replies
                            replies_data = comment.get('replies', {}).get('data', [])
                            for reply in replies_data:
                                reply_from = reply.get('from', {})
                                reply_user_id = reply_from.get('id')
                                reply_username = reply_from.get('username', '')

                                if reply_user_id:
                                    # Process reply user
                                    reply_user_info = {
                                        "id": reply_user_id,
                                        "username": reply_username
                                    }
                                    reply_user = InstagramService.process_user(reply_user_info)

                                    if reply_user:
                                        # Create reply comment using User model's method
                                        reply_doc = User.create_comment_document(
                                            post_id=post.get('id'),
                                            comment_id=reply.get('id'),
                                            text=reply.get('text', ''),
                                            parent_id=comment.get('id'),
                                            timestamp=parse_instagram_timestamp(reply.get('timestamp')),
                                            status="pending"
                                        )
                                        reply_doc["like_count"] = reply.get('like_count', 0)

                                        # Add reply to user's comments array
                                        User.add_comment_to_user(reply_user_id, reply_doc)

            return True

        except requests.exceptions.RequestException as req_err:
            logger.error(f"Error fetching posts: {str(req_err)}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error in get_posts: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def get_stories():
        """Retrieves stories from IG and stores them using the Story model"""
        try:
            base_endpoint = f"https://graph.facebook.com/v22.0/{Config.PAGE_ID}"
            story_endpoint = "/stories?fields=media_type,caption,like_count,thumbnail_url,timestamp&limit=1000"
            params = {"access_token": Config.FB_ACCESS_TOKEN}
            response = requests.get(base_endpoint + story_endpoint, params=params)
            response.raise_for_status()

            stories = response.json().get('data', [])

            for story in stories:
                story_data = {
                    "id": story.get('id'),
                    "media_type": story.get('media_type', ''),
                    "caption": story.get('caption', ''),
                    "like_count": story.get('like_count', 0),
                    "thumbnail_url": story.get('thumbnail_url'),
                    "timestamp": story.get('timestamp')
                }
                Story.create_or_update_from_instagram(story_data)

            return True

        except requests.exceptions.RequestException as req_err:
            logger.error(f"Error fetching stories: {str(req_err)}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error in get_stories: {str(e)}", exc_info=True)
            return False