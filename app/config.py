import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
load_dotenv()

class Config:
    MONGODB_URI = os.getenv('MONGODB_URI')
    MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME')

    VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
    BASE_URL = os.getenv('BASE_URL')
    PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
    FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN')
    PAGE_ID = os.getenv('PAGE_ID')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')
    BATCH_WINDOW_SECONDS = 30



