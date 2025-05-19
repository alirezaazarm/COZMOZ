from ..models.user import User
from ..models.database import USERS_COLLECTION, db

class UserRepository:
    def __init__(self, db_instance=None):
        self.db = db_instance or db