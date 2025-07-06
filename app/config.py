import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
load_dotenv()

class Config:
    # Database Configuration
    MONGODB_URI = os.getenv('MONGODB_URI')
    MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME')

    # System-wide Configuration
    VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
    BASE_URL = os.getenv('BASE_URL')
    BATCH_WINDOW_SECONDS = int(os.getenv('BATCH_WINDOW_SECONDS', '10'))
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

    # Development/Testing Fallback Credentials (optional)
    # These should only be used when no client is specified (backward compatibility)
    DEFAULT_PAGE_ACCESS_TOKEN = os.getenv('DEFAULT_PAGE_ACCESS_TOKEN', None)
    DEFAULT_FB_ACCESS_TOKEN = os.getenv('DEFAULT_FB_ACCESS_TOKEN', None)
    DEFAULT_PAGE_ID = os.getenv('DEFAULT_PAGE_ID', None)
    DEFAULT_OPENAI_API_KEY = os.getenv('DEFAULT_OPENAI_API_KEY', None)
    DEFAULT_OPENAI_ASSISTANT_ID = os.getenv('DEFAULT_OPENAI_ASSISTANT_ID', None)

    # Legacy properties for backward compatibility (deprecated - use client-specific credentials instead)
    @property
    def PAGE_ACCESS_TOKEN(self):
        logger.warning("PAGE_ACCESS_TOKEN is deprecated. Use client-specific credentials instead.")
        return self.DEFAULT_PAGE_ACCESS_TOKEN

    @property
    def FB_ACCESS_TOKEN(self):
        logger.warning("FB_ACCESS_TOKEN is deprecated. Use client-specific credentials instead.")
        return self.DEFAULT_FB_ACCESS_TOKEN

    @property
    def PAGE_ID(self):
        logger.warning("PAGE_ID is deprecated. Use client-specific credentials instead.")
        return self.DEFAULT_PAGE_ID

    @property
    def OPENAI_ASSISTANT_ID(self):
        logger.warning("OPENAI_ASSISTANT_ID is deprecated. Use client-specific credentials instead.")
        return self.DEFAULT_OPENAI_ASSISTANT_ID

    @classmethod
    def get_fallback_credentials(cls):
        """Get fallback credentials for backward compatibility"""
        return {
            'facebook': {
                'page_access_token': cls.DEFAULT_PAGE_ACCESS_TOKEN,
                'fb_access_token': cls.DEFAULT_FB_ACCESS_TOKEN,
                'page_id': cls.DEFAULT_PAGE_ID,
                'verify_token': cls.VERIFY_TOKEN
            },
            'openai': {
                'api_key': cls.DEFAULT_OPENAI_API_KEY,
                'assistant_id': cls.DEFAULT_OPENAI_ASSISTANT_ID
            }
        }



