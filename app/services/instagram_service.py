import requests
from ..config import Config
import logging
import re

logger = logging.getLogger(__name__)

class InstagramService:
    @staticmethod
    def send_message(recipient_id, text):
        # Check if the text contains multiple links
        link_pattern = re.compile(r'https?://\S+')
        links = link_pattern.findall(text)
        
        # If multiple links are found, split the message
        if len(links) > 1:
            logger.info(f"Found {len(links)} links in message, splitting into separate messages")
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
    def send_split_messages(recipient_id, text):
        """
        Splits a message containing multiple product entries and sends them as separate messages.
        Each product entry is expected to be a numbered item with details.
        """
        try:
            # Split the text by numbered list items (1., 2., etc.)
            # We're looking for patterns like "1. **Title**" or just numbered entries
            parts = re.split(r'\n\s*\d+\.\s+\*\*', text)
            
            if len(parts) <= 1:
                # Alternative splitting strategy if the above didn't work
                parts = re.split(r'\n\n\d+\.\s+', text)
                
            # If we have the header in the first part, send it separately
            success = True
            
            if parts[0] and not parts[0].startswith('**'):
                # Send the header text if it exists
                header = parts[0].strip()
                if header:
                    success = InstagramService.send_message_simple(recipient_id, header) and success
                parts = parts[1:]
            
            # Send each part as a separate message
            for i, part in enumerate(parts):
                if not part.strip():
                    continue
                    
                # Add back the number and formatting if we split on the pattern
                if not part.startswith('**'):
                    message = f"{i+1}. **{part}"
                else:
                    message = f"{i+1}. {part}"
                
                # Send the message and track overall success
                part_success = InstagramService.send_message_simple(recipient_id, message)
                success = success and part_success
                
                # Short delay between messages
                import time
                time.sleep(1)
                
            return success
        except Exception as e:
            logger.error(f"Failed to send split messages: {str(e)}")
            return False
    
    @staticmethod
    def send_message_simple(recipient_id, text):
        """
        Simple version of send_message without the splitting logic to avoid recursion.
        """
        try:
            logger.info(f"Sending part of split message to {recipient_id}")
            response = requests.post(
                "https://graph.instagram.com/v21.0/me/messages",
                headers={"Authorization": f"Bearer {Config.PAGE_ACCESS_TOKEN}"},
                json={"recipient": {"id": recipient_id}, "message": {"text": text}},
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Part of split message sent successfully to {recipient_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send part of split message: {str(e)}")
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