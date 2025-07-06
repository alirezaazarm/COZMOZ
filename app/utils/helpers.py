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

def fa_to_ar_text(text):
    """Convert Farsi/Persian characters to their Arabic equivalents"""
    # Comprehensive mapping of Farsi/Persian characters to Arabic characters
    fa_to_ar_mapping = {
        # Persian-specific letters to closest Arabic equivalents
        'ک': 'ك',  # Persian kaf to Arabic kaf
        'ی': 'ي',  # Persian yeh to Arabic yeh
        'پ': 'ب',  # Persian peh to Arabic beh
        'چ': 'ج',  # Persian cheh to Arabic jeem
        'ژ': 'ز',  # Persian zheh to Arabic zain
        'گ': 'غ',  # Persian gaf to Arabic ghain
        
        # Common Arabic letters (these remain the same but included for completeness)
        'ا': 'ا',  # alif
        'ب': 'ب',  # beh
        'ت': 'ت',  # teh
        'ث': 'ث',  # theh
        'ج': 'ج',  # jeem
        'ح': 'ح',  # hah
        'خ': 'خ',  # khah
        'د': 'د',  # dal
        'ذ': 'ذ',  # thal
        'ر': 'ر',  # reh
        'ز': 'ز',  # zain
        'س': 'س',  # seen
        'ش': 'ش',  # sheen
        'ص': 'ص',  # sad
        'ض': 'ض',  # dad
        'ط': 'ط',  # tah
        'ظ': 'ظ',  # zah
        'ع': 'ع',  # ain
        'غ': 'غ',  # ghain
        'ف': 'ف',  # feh
        'ق': 'ق',  # qaf
        'ل': 'ل',  # lam
        'م': 'م',  # meem
        'ن': 'ن',  # noon
        'ه': 'ه',  # heh
        'و': 'و',  # waw
        
        # Persian vowel marks and diacritics
        'َ': 'َ',   # fatha
        'ِ': 'ِ',   # kasra
        'ُ': 'ُ',   # damma
        'ً': 'ً',   # fathatan
        'ٍ': 'ٍ',   # kasratan
        'ٌ': 'ٌ',   # dammatan
        'ْ': 'ْ',   # sukun
        'ّ': 'ّ',   # shadda
        'ٰ': 'ٰ',   # alif khanjariyah
        
        # Persian-Indic to Arabic-Indic numerals
        '۰': '٠', '۱': '١', '۲': '٢', '۳': '٣', '۴': '٤', 
        '۵': '٥', '۶': '٦', '۷': '٧', '۸': '٨', '۹': '٩',
        
        # Additional Persian characters
        'آ': 'آ',  # alif with madda
        'ة': 'ة',  # teh marbuta
        'ى': 'ى',  # alif maksura
        'ء': 'ء',  # hamza
        'ؤ': 'ؤ',  # waw with hamza
        'ئ': 'ئ',  # yeh with hamza
        'إ': 'إ',  # alif with hamza below
        'أ': 'أ',  # alif with hamza above
        
        # Persian punctuation and symbols
        '؟': '؟',  # Arabic question mark
        '؛': '؛',  # Arabic semicolon
        '،': '،',  # Arabic comma
        '٪': '٪',  # Arabic percent sign
        '٫': '٫',  # Arabic decimal separator
        '٬': '٬',  # Arabic thousands separator
        
        # Zero-width characters
        '\u200c': '\u200c',  # zero-width non-joiner
        '\u200d': '\u200d',  # zero-width joiner
        '\u200e': '\u200e',  # left-to-right mark
        '\u200f': '\u200f',  # right-to-left mark
    }
    return ''.join([fa_to_ar_mapping.get(char, char) for char in text])

def expand_triggers(triggers_dict):
    """
    Expand each trigger in the dict to include its Persian, Arabic, and cross-script variants.
    For each trigger, adds the original, Persian numeral, Arabic numeral, and Farsi-to-Arabic text forms as keys (if different), all mapping to the same response.
    """
    expanded = {}
    for trigger, response in triggers_dict.items():
        expanded[trigger] = response
        
        # Convert English numbers to Farsi and Arabic numerals
        fa_nums = en_to_fa_number(trigger)
        ar_nums = en_to_ar_number(trigger)
        
        # Convert Farsi text to Arabic equivalent
        ar_text = fa_to_ar_text(trigger)
        
        # Add variants if they're different from original
        if fa_nums != trigger:
            expanded[fa_nums] = response
        if ar_nums != trigger and ar_nums != fa_nums:
            expanded[ar_nums] = response
        if ar_text != trigger and ar_text != fa_nums and ar_text != ar_nums:
            expanded[ar_text] = response
            
        # Also convert the Arabic text version's numerals
        if ar_text != trigger:
            ar_text_fa_nums = en_to_fa_number(ar_text)
            ar_text_ar_nums = en_to_ar_number(ar_text)
            if ar_text_fa_nums != ar_text and ar_text_fa_nums not in expanded:
                expanded[ar_text_fa_nums] = response
            if ar_text_ar_nums != ar_text and ar_text_ar_nums != ar_text_fa_nums and ar_text_ar_nums not in expanded:
                expanded[ar_text_ar_nums] = response
    
    return expanded

def load_main_app_globals_from_db():
    """
    Load all global variables in instagram_service.py from the database for all active clients.
    This should be called once at app startup to ensure all in-memory caches are populated.
    """
    import logging
    from app.models.client import Client
    from app.models.post import Post
    from app.models.story import Story
    from app.services import instagram_service
    logger = logging.getLogger(__name__)
    try:
        clients = Client.get_all_active()
        logger.info(f"Initializing InstagramService globals from DB for {len(clients)} active clients.")
        for client in clients:
            username = client.get('username')
            ig_id = client.get('keys', {}).get('ig_id')
            # 1. IG_ID_TO_CLIENT
            if ig_id and username:
                instagram_service.IG_ID_TO_CLIENT[ig_id] = username
            # 2. CLIENT_CREDENTIALS
            if username:
                instagram_service.CLIENT_CREDENTIALS[username] = client.get('keys', {})
            # 3. APP_SETTINGS
            if username:
                instagram_service.APP_SETTINGS[username] = {
                    'assistant': client.get('modules', {}).get('dm_assist', {}).get('enabled', False),
                    'fixed_responses': client.get('modules', {}).get('fixed_response', {}).get('enabled', False)
                }
            # 4. COMMENT_FIXED_RESPONSES
            if username:
                post_fixed = Post.get_all_fixed_responses_structured(username)
                instagram_service.COMMENT_FIXED_RESPONSES[username] = post_fixed
            # 5. STORY_FIXED_RESPONSES
            if username:
                story_fixed = Story.get_all_fixed_responses_structured(username)
                instagram_service.STORY_FIXED_RESPONSES[username] = story_fixed
            # 6. IG_CONTENT_IDS
            if username:
                post_ids = Post.get_post_ids(username)
                story_ids = Story.get_story_ids(username)
                instagram_service.IG_CONTENT_IDS[username] = {
                    'post_ids': post_ids,
                    'story_ids': story_ids
                }
        logger.info("InstagramService global variables initialized from DB.")
    except Exception as e:
        logger.error(f"Failed to initialize InstagramService globals from DB: {str(e)}", exc_info=True)
