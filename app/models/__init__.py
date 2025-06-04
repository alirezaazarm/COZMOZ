from .user import User
from .appsettings import AppSettings
from .product import Product
from .enums import UserStatus, MessageRole
from .additional_info import Additionalinfo
from .admin_user import AdminUser

# Initialize default app settings
default_settings = {
    "assistant": "false",
    "fixed_responses": "false",
    "vs_id":None
}

for key, value in default_settings.items():
    # check if the key already exists
    if not AppSettings.exist(key):
        # If it doesn't exist, create it
        AppSettings.create_or_update(key, value)

__all__ = ['User', 'AppSettings', 'Product', 'UserStatus', 'MessageRole', 'Story', 'Post', 'Additionalinfo', 'AdminUser']