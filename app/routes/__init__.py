from flask import Blueprint

routes_bp = Blueprint('routes', __name__)

from .webhook import webhook_bp
from .update import update_bp

routes_bp.register_blueprint(webhook_bp)
routes_bp.register_blueprint(update_bp)

__all__ = ['routes_bp']