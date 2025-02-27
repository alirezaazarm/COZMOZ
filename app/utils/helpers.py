import requests
import re
from datetime import datetime, UTC
from PIL import Image
from io import BytesIO
from werkzeug.utils import secure_filename
from sqlalchemy.exc import OperationalError, DisconnectionError, TimeoutError
from sqlalchemy.orm import Session
import logging
from ..services.instagram_service import InstagramService
from ..models.base import engine, SessionLocal
from ..config import Config
from ..models.user import User
from ..models.comment import Comment
from ..models.message import AssistantResponse, DirectMessage
from ..models.enums import MessageStatus, MessageDirection
from contextlib import contextmanager
from ..utils.exceptions import PermanentError
from sqlalchemy.exc import SQLAlchemyError


logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_content_type(url):
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
    print(f"Error fetching URL: {e}")
    return "unknown"


def download_image(url):
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


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'csv', 'pkl'}


def secure_filename_wrapper(filename):
    return secure_filename(filename)


def en_to_fa_number(number_str):
    mapping = {'0': '۰','1': '۱','2': '۲','3': '۳','4': '۴','5': '۵','6': '۶','7': '۷','8': '۸','9': '۹', }
    return ''.join([mapping.get(digit, digit) for digit in number_str])

def en_to_ar_number(number_str):
    mapping = {'0': '٠','1': '١','2': '٢','3': '٣','4': '٤','5': '٥','6': '٦','7': '٧','8': '٨','9': '٩', }
    return ''.join([mapping.get(digit, digit) for digit in number_str])

def reload_fixed_responses(fixed_responses, incoming):

    try:
        comment = {}
        direct = {}

        for resp in fixed_responses:
            trigger_keyword = str(resp['trigger_keyword'])

            if incoming == 'Comment':
                comment[trigger_keyword] = {'comment': resp['comment_response_text'], 'DM': resp['direct_response_text']}
                comment[en_to_fa_number(trigger_keyword)] = {'comment': resp['comment_response_text'], 'DM': resp['direct_response_text']}
                comment[en_to_ar_number(trigger_keyword)] = {'comment': resp['comment_response_text'], 'DM': resp['direct_response_text']}

            if incoming == "Direct":
                direct[trigger_keyword] = {'DM': resp['direct_response_text']}
                direct[en_to_fa_number(trigger_keyword)] = {'DM': resp['direct_response_text']}
                direct[en_to_ar_number(trigger_keyword)] = {'DM': resp['direct_response_text']}

        if incoming == 'Comment':
            global COMMENT_FIXED_RESPONSES
            COMMENT_FIXED_RESPONSES = comment
        if incoming == "Direct":
            global DIRECT_FIXED_RESPONSES
            DIRECT_FIXED_RESPONSES = direct

        return True
    except Exception as e:
        logging.info(f"Error occured when Reloading fixed comment responses: {e}")
        return False


def handle_message(db, message_data):
    try:
        logger.info(f"Processing message ID: {message_data.get('id')}")
        required_fields = ['id', 'from', 'recipient_id', 'timestamp']
        for field in required_fields:
            if field not in message_data:
                raise ValueError(f"Missing required field: {field}")

        sender_info = message_data['from']
        sender_info.setdefault('username', f"ig_user_{sender_info['id']}")
        sender_info.setdefault('full_name', '')
        sender_info.setdefault('profile_picture_url', '')

        sender = process_user(db, sender_info)
        recipient = process_user(db, {
            'id': message_data['recipient_id'],
            'username': f"ig_business_{message_data['recipient_id']}",
            'full_name': '',
            'profile_picture_url': ''
        })

        message_text = message_data.get('text', '')

        if not message_text:
            fixed_response = 'محتوایی که به اشتراک گذاشتید، برای من دردسترس نیست. لطفا ازش اسکرین شات بگیرید تا منم بتونم ببینمش'
            success = InstagramService.send_message(sender.user_id, fixed_response)
            if success:
                logger.info("Fixed response sent successfully")
                return True
            else:
                logger.error("Failed to send fixed response")
                return False

        elif "DIRECT_FIXED_RESPONSES" in globals() and DIRECT_FIXED_RESPONSES.get(message_text):
            fixed_response = DIRECT_FIXED_RESPONSES.get(message_text)
            print("Config.DIRECT_FIXED_RESPONSES::::::::::::", DIRECT_FIXED_RESPONSES)

            success = InstagramService.send_message(sender.user_id, fixed_response['DM'])
            if success:
                logger.info("Fixed response sent successfully")
                return True
            else:
                logger.error("Failed to send fixed response")
                return False

        else:
            message = DirectMessage(
                message_id=message_data['id'],
                sender_id=sender.user_id,
                recipient_id=recipient.user_id,
                message_text=message_data.get('text'),
                timestamp=message_data['timestamp'],
                direction=MessageDirection.INCOMING,
                status=MessageStatus.PENDING,
                media_type=message_data.get('media_type'),
                media_url=message_data.get('media_url')
            )
            db.add(message)
            logger.debug(f"Added message {message.message_id} to database")
            return True

    except ValueError as ve:
        logger.error(f"Invalid message data: {str(ve)}")
        db.rollback()
        return False

    except Exception as e:
        logger.error(f"Unexpected error in handle_message: {str(e)}", exc_info=True)
        db.rollback()
        return False


def update_comment_status(db, comment_id, status):
    try:
        comment = db.query(Comment).filter(Comment.comment_id == comment_id).first()
        if comment:
            comment.status = status
            db.commit()
            logger.info(f"Updated status of comment {comment_id} to {status}")
            return True
        else:
            logger.warning(f"Comment {comment_id} not found")
            return False
    except Exception as e:
        logger.error(f"Failed to update comment status: {str(e)}")
        db.rollback()
        return False


def handle_comment(db, comment_data):
    try:
        logger.info(f"Processing comment ID: {comment_data.get('comment_id')}")
        required_fields = ['comment_id', 'post_id', 'user_id', 'comment_text', 'timestamp']
        for field in required_fields:
            if field not in comment_data:
                raise ValueError(f"Missing required field: {field}")

        created_time = comment_data.get('created_time')
        if created_time:
            try:
                timestamp = datetime.fromtimestamp(created_time, UTC).replace(tzinfo=None)
            except Exception as e:
                logger.error(f"Failed to parse timestamp for comment {comment_data['comment_id']}: {str(e)}")
                timestamp = datetime.now(UTC)
        else:
            logger.warning(f"No 'created_time' found for comment {comment_data['comment_id']}. Using current time.")
            timestamp = datetime.now(UTC)

        user_info = {
            'id': comment_data['user_id'],
            'username': comment_data.get('username', f"ig_user_{comment_data['user_id']}"),
            'full_name': '',
            'profile_picture_url': ''
        }

        parent_comment_id = comment_data.get('parent_comment_id')
        if parent_comment_id:
            parent_comment = db.query(Comment).filter(Comment.comment_id == parent_comment_id).first()
            if not parent_comment:
                logger.warning(f"Parent comment {parent_comment_id} not found. Skipping reply.")
                return False

        user = process_user(db, user_info)

        comment = Comment(
            comment_id=comment_data['comment_id'],
            post_id=comment_data['post_id'],
            user_id=user.user_id,
            comment_text=comment_data['comment_text'],
            parent_comment_id=parent_comment_id,
            timestamp=timestamp,
            status=comment_data.get('status', 'not_replied')
        )

        db.add(comment)
        db.flush()

        if "COMMENT_FIXED_RESPONSES" in globals() and COMMENT_FIXED_RESPONSES.get(comment_data['comment_text']):
            fixed_response = COMMENT_FIXED_RESPONSES.get(comment_data['comment_text'])
            print("Config.COMMENT_FIXED_RESPONSES::::::::::", COMMENT_FIXED_RESPONSES)
            DM_reply = fixed_response.get('DM', '')
            comment_reply = fixed_response.get('comment', '')
            replied_in_direct = False
            replied_in_comment = False

            if DM_reply:
                success_DM = InstagramService.send_message(comment_data['user_id'], DM_reply)
                if success_DM:
                    replied_in_direct = True
                    logger.info("Fixed DM response sent successfully")
                else:
                    logger.error("Failed to send fixed DM response")

            if comment_reply:
                success_comment = InstagramService.send_comment_reply(comment_data['comment_id'], comment_reply)
                if success_comment:
                    replied_in_comment = True
                    logger.info("Fixed comment reply sent successfully")
                else:
                    logger.error("Failed to send fixed comment reply")

            if replied_in_direct and replied_in_comment:
                update_comment_status(db, comment.comment_id, "replied_in_cm_DM")
            elif replied_in_direct:
                update_comment_status(db, comment.comment_id, "replied_in_DM")
            elif replied_in_comment:
                update_comment_status(db, comment.comment_id, "replied_in_cm")
            else:
                update_comment_status(db, comment.comment_id, "not_replied")




        db.commit()
        logger.debug(f"Added comment {comment.comment_id} to database")
        return True

    except ValueError as ve:
        logger.error(f"Invalid comment data: {str(ve)}")
        db.rollback()
        return False

    except SQLAlchemyError as se:
        logger.error(f"Database error: {str(se)}")
        db.rollback()
        return False

    except Exception as e:
        logger.error(f"Unexpected error in handle_comment: {str(e)}", exc_info=True)
        db.rollback()
        return False


def handle_instagram_outcome(db, messages, success):
    status = (
        MessageStatus.REPLIED_TO_INSTAGRAM
        if success
        else MessageStatus.INSTAGRAM_FAILED
    )
    try:
        with db.begin_nested():
            for msg in messages:
                msg.status = status.value

            message_ids = [msg.message_id for msg in messages]
            db.query(AssistantResponse).filter(
                AssistantResponse.message_ids.contains(message_ids)
            ).update(
                {"instagram_status": status.value},
                synchronize_session="fetch"
            )
        logger.info(f"Updated status to {status} for {len(messages)} messages")

    except Exception as e:
        logger.error(f"Failed to update Instagram outcome: {str(e)}")


def process_user(db, user_data):
    try:
        user_id = user_data['id']
        username = user_data.get('username', f"ig_user_{user_id}")
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            logger.info(f"Creating user {username} ({user_id})")
            user = User(
                user_id=user_id,
                username=username,
                full_name=user_data.get('full_name'),
                profile_picture_url=user_data.get('profile_picture_url')
            )
            db.add(user)
        return user

    except KeyError as ke:
        logger.error(f"Invalid user data: Missing {str(ke)}")
        raise

    except Exception as e:
        logger.error(f"User processing error: {str(e)}")
        raise


def safe_db_operation(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (OperationalError, TimeoutError, DisconnectionError) as e:
            logger.warning(f"Database connection error: {str(e)}")
            engine.dispose()
            raise
    return wrapper


def handle_batch_error(db: Session, error: Exception, messages):
    try:
        with db.begin_nested():
            if isinstance(error, PermanentError):
                new_status = MessageStatus.ASSISTANT_FAILED.value
            else:
                new_status = MessageStatus.PENDING.value
            for msg in messages:
                msg.status = new_status
            db.query(AssistantResponse).filter(
                AssistantResponse.message_ids.contains([msg.message_id for msg in messages])
            ).update({"assistant_status": new_status}, synchronize_session=False)
            db.commit()
    except Exception as e:
        logger.critical("Error recovery failed!", exc_info=True)
        db.rollback()


def clean_openai_response(response_text):
    metadata_pattern = r"【\d+:\d+†source】"
    cleaned_text = re.sub(metadata_pattern, "", response_text).strip()
    return cleaned_text



