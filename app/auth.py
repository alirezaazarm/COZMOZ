"""Authentication and authorization helpers for the browser-facing API."""

from __future__ import annotations

from functools import wraps
import secrets

from flask import g, jsonify, request, session

from .config import Config
from .models.client import Client


def public_account(account: dict) -> dict:
    return {
        "username": account["username"],
        "business_name": account.get("business_name") or account.get("info", {}).get("business"),
        "role": account.get("role", "tenant_admin"),
        "is_system_admin": is_system_admin(account),
    }


def is_system_admin(account: dict) -> bool:
    return (
        account.get("role") == "system_admin"
        or account.get("username") in Config.SYSTEM_ADMIN_USERNAMES
    )


def login_account(account: dict) -> dict:
    session.clear()
    session["username"] = account["username"]
    session["csrf_token"] = secrets.token_urlsafe(32)
    return public_account(account)


def current_account() -> dict | None:
    username = session.get("username")
    if not username:
        return None
    account = Client.get_by_username(username)
    if not account or account.get("status") in {"inactive", "deleted"}:
        session.clear()
        return None
    return account


def api_auth(system_admin: bool = False):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            account = current_account()
            if account is None:
                return jsonify({"error": {"code": "unauthorized", "message": "Sign in is required."}}), 401
            if system_admin and not is_system_admin(account):
                return jsonify({"error": {"code": "forbidden", "message": "System administrator access is required."}}), 403
            g.account = account
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_csrf(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = session.get("csrf_token")
        supplied = request.headers.get("X-CSRF-Token")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            return jsonify({"error": {"code": "csrf_failed", "message": "The security token is missing or invalid."}}), 403
        return view(*args, **kwargs)

    return wrapped
