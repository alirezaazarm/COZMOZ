import requests
from ..config import Config
import logging

logger = logging.getLogger(__name__)

class InstagramService:
    def send_message(recipient_id, text):
        try:
            response = requests.post(
                "https://graph.instagram.com/v21.0/me/messages",
                headers={"Authorization": f"Bearer {Config.PAGE_ACCESS_TOKEN}"},
                json={"recipient": {"id": recipient_id}, "message": {"text": text}},
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Instagram send failed: {str(e)}")
            return False

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