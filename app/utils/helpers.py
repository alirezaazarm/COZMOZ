from werkzeug.utils import secure_filename
import logging
from ..models.database import db
from contextlib import contextmanager
from pymongo.errors import PyMongoError


logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    try:
        yield db
    except Exception:
        raise
    finally:
        pass


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'pt'}


def secure_filename_wrapper(filename):
    return secure_filename(filename)


def en_to_fa_number(number_str):
    mapping = {'0': '۰','1': '۱','2': '۲','3': '۳','4': '۴','5': '۵','6': '۶','7': '۷','8': '۸','9': '۹', }
    return ''.join([mapping.get(digit, digit) for digit in number_str])

def en_to_ar_number(number_str):
    mapping = {'0': '٠','1': '١','2': '٢','3': '٣','4': '٤','5': '٥','6': '٦','7': '٧','8': '٨','9': '٩', }
    return ''.join([mapping.get(digit, digit) for digit in number_str])


def safe_db_operation(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (PyMongoError) as e:
            logger.warning(f"Database connection error: {str(e)}")
            raise
    return wrapper
