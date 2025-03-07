import os
from dotenv import load_dotenv
from sqlalchemy.pool import QueuePool
import logging

logger = logging.getLogger(__name__)
load_dotenv()

class Config:
    DATABASE_URL = os.getenv('DATABASE_URL')
    VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
    BASE_URL = os.getenv('BASE_URL')
    PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')
    OPENAI_TRANSLATOR_ID =  os.getenv('OPENAI_TRANSLATOR_ID')
    VECTOR_DSORE_ID = os.getenv('VECTOR_DSORE_ID')
    POOL_CLASS = QueuePool
    BATCH_WINDOW_SECONDS = 30



