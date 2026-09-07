"""Versioned, browser-facing API for the unified management application."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import time

from bson import ObjectId
from flask import Blueprint, Response, g, jsonify, request, session, stream_with_context
from pymongo import ASCENDING, DESCENDING

from ..auth import api_auth, current_account, login_account, public_account, require_csrf
from ..config import Config
from ..models.additional_info import Additionalinfo
from ..models.client import Client
from ..models.database import (
    ADDITIONAL_TEXT_COLLECTION,
    CLIENTS_COLLECTION,
    POSTS_COLLECTION,
    PRODUCTS_COLLECTION,
    STORIES_COLLECTION,
    USERS_COLLECTION,
    db,
)
from ..models.enums import ClientStatus, MessageRole, Platform, UserStatus
from ..models.product import Product
from ..services.AI.openai_service import OpenAIService
from ..services.platforms.instagram import InstagramService
from ..services.platforms.telegram import TelegramService
from ..services.platforms.bale import BaleService
from ..utils.helpers import load_main_app_globals_from_db

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

MAX_PAGE_SIZE = 100
SAFE_CLIENT_FIELDS = {"status", "notes", "info", "platforms", "settings"}
SECRET_FIELDS = {"page_access_token", "facebook_access_token", "telegram_access_token", "bale_access_token", "password"}


def json_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        # Mongo returns naive UTC datetimes (tz_aware=False). Treat naive as UTC
        # and always emit ISO with timezone so JS `new Date()` parses as UTC, not local.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    return value


def response(data, status=200):
    return jsonify({"data": json_value(data)}), status


def error(message, status=400, code="validation_error"):
    return jsonify({"error": {"code": code, "message": message}}), status


def body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def page_params():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        limit = min(max(int(request.args.get("limit", 25)), 1), MAX_PAGE_SIZE)
    except ValueError:
        return None
    return page, limit


def scoped_client() -> str:
    return g.account["username"]


def client_summary(client: dict) -> dict:
    return {
        "username": client["username"],
        "business_name": client.get("business_name") or client.get("info", {}).get("business"),
        "email": client.get("email") or client.get("info", {}).get("email"),
        "status": client.get("status"),
        "platforms": client.get("platforms", {}),
        "created_at": client.get("created_at"),
        "updated_at": client.get("updated_at"),
    }


def content_collection(kind: str):
    if kind == "posts":
        return POSTS_COLLECTION
    if kind == "stories":
        return STORIES_COLLECTION
    return None


def public_content(document: dict) -> dict:
    source = document.get("source") or {}
    return {
        "id": str(document.get("_id")),
        "source_id": document.get("id"),
        "platform": source.get("platform") or document.get("platform"),
        "account_username": source.get("account_username"),
        "caption": document.get("caption", ""),
        "media_url": document.get("media_url"),
        "thumbnail_url": document.get("thumbnail_url"),
        "media_type": document.get("media_type"),
        "timestamp": document.get("timestamp"),
        "like_count": document.get("like_count", 0),
        "label": document.get("label", ""),
        "admin_explanation": document.get("admin_explanation"),
        "fixed_responses": document.get("fixed_responses", []),
        "children": document.get("children", []),
    }


@api_bp.post("/auth/login")
def login():
    payload = body()
    username = str(payload.get("username", "")).strip()
    password = payload.get("password")
    if not username or not isinstance(password, str):
        return error("Username and password are required.", 400)
    account = Client.authenticate(username, password)
    if not account:
        return error("Invalid username or password.", 401, "invalid_credentials")
    return response({"account": login_account(account), "csrf_token": session["csrf_token"]})


@api_bp.post("/auth/logout")
@api_auth()
@require_csrf
def logout():
    session.clear()
    return response({"logged_out": True})


@api_bp.get("/auth/me")
def me():
    account = current_account()
    if account is None:
        return error("Sign in is required.", 401, "unauthorized")
    return response({"account": public_account(account), "csrf_token": session["csrf_token"]})


@api_bp.get("/dashboard")
@api_auth()
def dashboard():
    client = scoped_client()
    since = datetime.now(timezone.utc) - timedelta(days=30)
    return response(
        {
            "counts": {
                "users": db[USERS_COLLECTION].count_documents({"source.client_username": client}),
                "products": db[PRODUCTS_COLLECTION].count_documents({"client_username": client}),
                "posts": db[POSTS_COLLECTION].count_documents({"source.client_username": client}),
                "stories": db[STORIES_COLLECTION].count_documents({"source.client_username": client}),
            },
            "status_counts": UserStatusCounts(client),
            "recent_messages": UserMessageCounts(client, since),
            "platforms": g.account.get("platforms", {}),
        }
    )


def UserStatusCounts(client: str) -> dict:
    pipeline = [{"$match": {"source.client_username": client}}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    return {item["_id"]: item["count"] for item in db[USERS_COLLECTION].aggregate(pipeline)}


def UserMessageCounts(client: str, since: datetime) -> dict:
    pipeline = [
        {"$match": {"source.client_username": client}},
        {"$project": {"direct_messages": {"$filter": {
            "input": "$direct_messages",
            "as": "message",
            "cond": {"$gte": ["$$message.timestamp", since]},
        }}}},
        {"$unwind": "$direct_messages"},
        {"$group": {"_id": "$direct_messages.role", "count": {"$sum": 1}}},
    ]
    return {item["_id"]: item["count"] for item in db[USERS_COLLECTION].aggregate(pipeline)}


@api_bp.get("/products")
@api_auth()
def products():
    params = page_params()
    if params is None:
        return error("Invalid pagination parameters.")
    page, limit = params
    query = {"client_username": scoped_client()}
    search = request.args.get("search", "").strip()
    if search:
        query["$or"] = [
            {"title": {"$regex": re.escape(search), "$options": "i"}},
            {"sku": {"$regex": re.escape(search), "$options": "i"}},
            {"category": {"$regex": re.escape(search), "$options": "i"}},
        ]
    total = db[PRODUCTS_COLLECTION].count_documents(query)
    items = list(db[PRODUCTS_COLLECTION].find(query).skip((page - 1) * limit).limit(limit))
    return response({"items": items, "page": page, "limit": limit, "total": total})


@api_bp.patch("/products/<product_id>")
@api_auth()
@require_csrf
def update_product(product_id):
    payload = body()
    allowed = {"title", "category", "tags", "price", "excerpt", "sku", "description", "stock_status", "additional_info"}
    updates = {key: value for key, value in payload.items() if key in allowed}
    if not updates:
        return error("No supported product fields were supplied.")
    try:
        result = db[PRODUCTS_COLLECTION].update_one(
            {"_id": ObjectId(product_id), "client_username": scoped_client()}, {"$set": updates}
        )
    except Exception:
        return error("Invalid product identifier.", 404, "not_found")
    if not result.matched_count:
        return error("Product not found.", 404, "not_found")
    return response({"updated": True})


@api_bp.get("/knowledge")
@api_auth()
def knowledge():
    params = page_params()
    if params is None:
        return error("Invalid pagination parameters.")
    page, limit = params
    query = {"client_username": scoped_client()}
    total = db["additional_info"].count_documents(query)
    items = list(db["additional_info"].find(query).sort("title", ASCENDING).skip((page - 1) * limit).limit(limit))
    return response({"items": items, "page": page, "limit": limit, "total": total})


@api_bp.post("/knowledge")
@api_auth()
@require_csrf
def create_knowledge():
    payload = body()
    title = str(payload.get("title", "")).strip()
    content = payload.get("content")
    content_format = payload.get("content_format", "markdown")
    if not title or not isinstance(content, str) or content_format not in {"markdown", "json"}:
        return error("A title, content, and supported content format are required.")
    if content_format == "json" and not Additionalinfo.validate_json_content(content):
        return error("JSON knowledge must contain valid JSON.")
    created = Additionalinfo.create(title, content, scoped_client(), content_format=content_format)
    if not created:
        return error("Knowledge entry could not be saved.", 500, "persistence_failed")
    return response(created, 201)


@api_bp.put("/knowledge/<entry_id>")
@api_auth()
@require_csrf
def replace_knowledge(entry_id):
    payload = body()
    allowed = {"title", "content", "content_format"}
    updates = {key: value for key, value in payload.items() if key in allowed}
    if updates.get("content_format") == "json" and not Additionalinfo.validate_json_content(updates.get("content")):
        return error("JSON knowledge must contain valid JSON.")
    try:
        matched = db["additional_info"].update_one(
            {"_id": ObjectId(entry_id), "client_username": scoped_client()}, {"$set": updates}
        ).matched_count
    except Exception:
        return error("Invalid knowledge identifier.", 404, "not_found")
    if not matched:
        return error("Knowledge entry not found.", 404, "not_found")
    return response({"updated": True})


@api_bp.delete("/knowledge/<entry_id>")
@api_auth()
@require_csrf
def delete_knowledge(entry_id):
    try:
        deleted = db["additional_info"].delete_one(
            {"_id": ObjectId(entry_id), "client_username": scoped_client()}
        ).deleted_count
    except Exception:
        return error("Invalid knowledge identifier.", 404, "not_found")
    if not deleted:
        return error("Knowledge entry not found.", 404, "not_found")
    return response({"deleted": True})


@api_bp.get("/agents")
@api_auth()
def agents():
    return response(Client.get_agents(scoped_client()))


# Cache for OpenAI models list (shared across requests, 1h TTL)
_openai_models_cache = {"ts": 0.0, "models": None}

def _get_openai_models():
    """Fetch model IDs live from OpenAI API only (no static fallback), cached 1h."""
    import time as _time
    now = _time.time()
    cached = _openai_models_cache.get("models")
    ts = _openai_models_cache.get("ts", 0)
    if cached is not None and (now - ts) < 3600:
        return cached
    api_key = Config.OPENAI_API_KEY
    if not api_key:
        logging.getLogger(__name__).warning("OPENAI_API_KEY not set — returning empty models list (API-only mode).")
        _openai_models_cache["models"] = []
        _openai_models_cache["ts"] = now
        return []
    try:
        import openai as _openai
        _client = _openai.OpenAI(api_key=api_key, timeout=12.0)
        resp = _client.models.list()
        ids = [m.id for m in getattr(resp, "data", []) or [] if getattr(m, "id", None)]
        if not ids:
            raise ValueError("Empty models list from OpenAI")
        def _sort_key(x: str):
            xl = x.lower()
            if "gpt-4.1" in xl: return (0, xl)
            if "gpt-4o" in xl: return (1, xl)
            if "gpt-4" in xl: return (2, xl)
            if "gpt-3.5" in xl: return (3, xl)
            if xl.startswith("o1"): return (4, xl)
            if "gpt" in xl: return (5, xl)
            return (10, xl)
        models = sorted(ids, key=_sort_key)
        _openai_models_cache["models"] = models
        _openai_models_cache["ts"] = now
        return models
    except Exception as exc:
        logging.getLogger(__name__).warning(f"OpenAI models fetch failed (API-only mode): {exc}")
        # Return cached if any, otherwise empty — no static fallback
        if cached is not None:
            return cached
        _openai_models_cache["models"] = []
        _openai_models_cache["ts"] = now
        return []

@api_bp.get("/agents/options")
@api_auth()
def agent_options():
    """Models, stored vector stores, and platform accounts for the agent form."""
    client = Client.get_by_username(scoped_client())
    accounts = []
    for platform_name, platform_data in (client.get("platforms", {}) or {}).items():
        for acc in platform_data.get("accounts", []):
            accounts.append({
                "id": acc.get("id"),
                "platform": platform_name,
                "name": acc.get("name"),
                "username": acc.get("username") or acc.get("bot_username"),
                "status": acc.get("status"),
            })
    # Live list from OpenAI API only (no static Config.AVAILABLE_MODELS fallback)
    models = _get_openai_models()
    # Allow manual refresh: /agents/options?refresh=1 bypasses cache
    if request.args.get("refresh") == "1":
        _openai_models_cache["ts"] = 0
        models = _get_openai_models()
    return response({
        "models": models,
        "vector_store_ids": Client._normalize_vector_store_ids(
            (client.get("keys", {}) or {}).get("vector_store_id")
        ),
        "accounts": accounts,
    })


@api_bp.post("/agents/<agent_id>/test")
@api_auth()
@require_csrf
def test_agent(agent_id):
    payload = body()
    message = str(payload.get("message", "")).strip()
    image = payload.get("image")
    conversation_id = payload.get("conversation_id")
    if len(message) > 4000:
        return error("Test message must be at most 4,000 characters.")
    if image is not None and (
        not isinstance(image, str)
        or not image.startswith("data:image/")
        or len(image) > 7_000_000
    ):
        return error("Test image must be a base64 data URL of at most ~5 MB.")
    if conversation_id is not None and (not isinstance(conversation_id, str) or len(conversation_id) > 128):
        return error("Invalid test conversation id.")
    if not message and not image:
        return error("A test message or image is required.")
    agent = next((a for a in Client.get_agents(scoped_client()) if a.get("id") == agent_id), None)
    if not agent:
        return error("Agent not found.", 404, "not_found")
    try:
        reply, conversation_id = OpenAIService(client_username=scoped_client()).preview_agent(
            agent, message, conversation_id=conversation_id, image=image
        )
    except Exception as exc:
        return error(f"Agent test failed: {exc}", 502, "agent_test_failed")
    return response({"reply": reply, "conversation_id": conversation_id, "model": agent.get("model")})


@api_bp.post("/agents")
@api_auth()
@require_csrf
def create_agent():
    payload = body()
    agent = Client.add_agent(
        scoped_client(),
        status=payload.get("status"),
        platform=payload.get("platform"),
        account_id=payload.get("account_id"),
        instruction=payload.get("instruction", ""),
        model=payload.get("model"),
        title=payload.get("title", ""),
        vector_store_id=payload.get("vector_store_id") or None,
    )
    if not agent:
        return error("Agent could not be created. Check its model, platform, account, and vector store.", 400)
    return response(agent, 201)


@api_bp.patch("/agents/<agent_id>")
@api_auth()
@require_csrf
def update_agent(agent_id):
    payload = body()
    if not Client.update_agent(scoped_client(), agent_id, payload):
        return error("Agent could not be updated.", 400)
    return response({"updated": True})


@api_bp.delete("/agents/<agent_id>")
@api_auth()
@require_csrf
def delete_agent(agent_id):
    if not Client.remove_agent(scoped_client(), agent_id):
        return error("Agent not found.", 404, "not_found")
    return response({"deleted": True})


@api_bp.get("/content/<kind>")
@api_auth()
def list_content(kind):
    collection = content_collection(kind)
    if not collection:
        return error("Unknown content type.", 404, "not_found")
    params = page_params()
    if params is None:
        return error("Invalid pagination parameters.")
    page, limit = params
    query = {"source.client_username": scoped_client()}
    label = request.args.get("label")
    if label is not None:
        query["label"] = label
    total = db[collection].count_documents(query)
    documents = db[collection].find(query).sort("timestamp", DESCENDING).skip((page - 1) * limit).limit(limit)
    return response({"items": [public_content(item) for item in documents], "page": page, "limit": limit, "total": total})


@api_bp.patch("/content/<kind>/<source_id>")
@api_auth()
@require_csrf
def update_content(kind, source_id):
    collection = content_collection(kind)
    if not collection:
        return error("Unknown content type.", 404, "not_found")
    payload = body()
    allowed = {"label", "admin_explanation", "fixed_responses"}
    updates = {key: value for key, value in payload.items() if key in allowed}
    if not updates:
        return error("No supported content fields were supplied.")
    result = db[collection].update_one(
        {"id": source_id, "source.client_username": scoped_client()}, {"$set": updates}
    )
    if not result.matched_count:
        return error("Content item not found.", 404, "not_found")
    load_main_app_globals_from_db()
    return response({"updated": True})


def conversation_filters(params=None):
    """Build a MongoDB query for conversations from request args or a payload dict."""
    source = params if params is not None else request.args
    query = {"source.client_username": scoped_client()}
    platform = source.get("platform")
    status = source.get("status")
    username = str(source.get("username", "")).strip()
    search = str(source.get("search", "")).strip()
    date_from = str(source.get("date_from", "")).strip()
    date_to = str(source.get("date_to", "")).strip()
    if platform in {item.value for item in Platform}:
        query["source.platform"] = platform
    account = str(source.get("account", "")).strip().lstrip("@")
    if account:
        query["source.account_username"] = account
    if status in {item.value for item in UserStatus}:
        query["status"] = status
    # Legacy narrow filter (username field only). Kept for backward compatibility;
    # the UI uses `search`, which is a strict superset (username + names + text + …).
    if username:
        query["username"] = {"$regex": re.escape(username), "$options": "i"}
    updated_window = {}
    for key, raw, end in (("$gte", date_from, False), ("$lt", date_to, True)):
        if raw:
            try:
                parsed = datetime.fromisoformat(raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if end:
                    parsed += timedelta(days=1)
                updated_window[key] = parsed
            except ValueError:
                pass
    if updated_window:
        query["updated_at"] = updated_window
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [
            {"username": pattern},
            {"first_name": pattern},
            {"last_name": pattern},
            {"user_id": pattern},
            {"status": pattern},
            {"source.account_username": pattern},
            {"direct_messages.text": pattern},
        ]
    return query


@api_bp.get("/conversations")
@api_auth()
def conversations():
    params = page_params()
    if params is None:
        return error("Invalid pagination parameters.")
    page, limit = params
    query = conversation_filters()
    projection = {"direct_messages": {"$slice": -1}, "response_id": 0}
    total = db[USERS_COLLECTION].count_documents(query)
    items = list(db[USERS_COLLECTION].find(query, projection).sort("updated_at", DESCENDING).skip((page - 1) * limit).limit(limit))
    for item in items:
        source = item.get("source") or {}
        item["platform"] = source.get("platform") or item.get("platform")
        item["client_username"] = source.get("client_username") or item.get("client_username")
        item["account_username"] = source.get("account_username")
    return response({"items": items, "page": page, "limit": limit, "total": total})


@api_bp.get("/conversations/<user_id>/messages")
@api_auth()
def conversation_messages(user_id):
    platform = request.args.get("platform")
    if platform not in {item.value for item in Platform}:
        return error("A supported conversation platform is required.")
    query = {"source.client_username": scoped_client(), "user_id": user_id, "source.platform": platform}
    account = str(request.args.get("account", "")).strip().lstrip("@")
    if account:
        query["source.account_username"] = account
    conversation = db[USERS_COLLECTION].find_one(
        query,
        {"direct_messages": {"$slice": -100}, "_id": 0},
    )
    if not conversation:
        return error("Conversation not found.", 404, "not_found")
    return response(conversation["direct_messages"])


@api_bp.post("/conversations/<user_id>/messages")
@api_auth()
@require_csrf
def send_message(user_id):
    text = body().get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return error("Message text is required and must be at most 4,000 characters.")
    platform = request.args.get("platform")
    if platform not in {item.value for item in Platform}:
        return error("A supported conversation platform is required.")
    conversation_query = {"source.client_username": scoped_client(), "user_id": user_id, "source.platform": platform}
    account = str(request.args.get("account", "")).strip().lstrip("@")
    if account:
        conversation_query["source.account_username"] = account
    conversation = db[USERS_COLLECTION].find_one(conversation_query)
    if not conversation:
        return error("Conversation not found.", 404, "not_found")
    if (conversation.get("source") or {}).get("platform") == Platform.TELEGRAM.value:
        sent = TelegramService.send_message(user_id, text.strip(), scoped_client(), account_username=account or (conversation.get("source") or {}).get("account_username"))
    elif (conversation.get("source") or {}).get("platform") == Platform.BALE.value:
        sent = BaleService.send_message(user_id, text.strip(), scoped_client(), account_username=account or (conversation.get("source") or {}).get("account_username"))
    else:
        sent = InstagramService.send_message(user_id, text.strip(), scoped_client(), account_username=account or (conversation.get("source") or {}).get("account_username"))
    if not sent:
        return error("The platform rejected the message. Check the platform configuration.", 502, "platform_rejected")
    message = {
        "message_id": str(sent),
        "text": text.strip(),
        "role": MessageRole.ADMIN.value,
        "timestamp": datetime.now(timezone.utc),
    }
    db[USERS_COLLECTION].update_one(
        {"_id": conversation["_id"]},
        {"$push": {"direct_messages": message}, "$set": {"status": UserStatus.ADMIN_REPLIED.value, "updated_at": datetime.now(timezone.utc)}},
    )
    return response(message, 201)


@api_bp.get("/conversations/stream")
@api_auth()
def conversations_stream():
    """SSE stream for conversation list — realtime with DB.

    Reuses the same query filters as GET /conversations (platform, account,
    status, date_from, date_to, search, page, limit) and pushes an event
    whenever the filtered set changes. Polling-based so it works without a
    Mongo replica set / change stream; the client (EventSource) will
    auto-reconnect on disconnect.
    """
    # Capture immutable filter snapshot outside generator so request context is not needed inside
    # But we need to re-evaluate on each loop from current request args — args are static
    # per connection; the stream reflects the subscription as opened.
    query = conversation_filters()
    params = page_params()
    if params is None:
        page, limit = 1, 25
    else:
        page, limit = params

    def generate():
        import hashlib

        last_hash = None
        heartbeat_counter = 0
        while True:
            try:
                projection = {"direct_messages": {"$slice": -1}, "response_id": 0}
                total = db[USERS_COLLECTION].count_documents(query)
                items = list(
                    db[USERS_COLLECTION].find(query, projection)
                    .sort("updated_at", DESCENDING)
                    .skip((page - 1) * limit)
                    .limit(limit)
                )
                for item in items:
                    source = item.get("source") or {}
                    item["platform"] = source.get("platform") or item.get("platform")
                    item["client_username"] = source.get("client_username") or item.get("client_username")
                    item["account_username"] = source.get("account_username")

                payload = json_value({"items": items, "page": page, "limit": limit, "total": total})

                # Change detection hash: total + ordered list of (user_id, updated_at)
                hash_input_parts = [str(total)]
                for it in items:
                    # updated_at is now an ISO string after json_value
                    hash_input_parts.append(f"{it.get('user_id')}|{it.get('updated_at')}|{it.get('status')}")
                    # also include last message text snippet for new message detection
                    dm = (it.get("direct_messages") or [])
                    if dm:
                        hash_input_parts.append(str(dm[0].get("timestamp") or "") + str(dm[0].get("text") or "")[:40])
                cur_hash = hashlib.md5("|".join(hash_input_parts).encode()).hexdigest()

                if cur_hash != last_hash:
                    last_hash = cur_hash
                    data = json.dumps(payload)
                    yield f"event: conversations\ndata: {data}\n\n"
                    heartbeat_counter = 0
                else:
                    heartbeat_counter += 1
                    if heartbeat_counter % 8 == 0:
                        yield ": heartbeat\n\n"
                time.sleep(2)
            except GeneratorExit:
                break
            except Exception as exc:
                # Emit error event but keep stream alive; client may reconnect
                try:
                    yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
                except Exception:
                    pass
                time.sleep(5)

    return _sse_response(generate)


@api_bp.get("/conversations/<user_id>/messages/stream")
@api_auth()
def conversation_messages_stream(user_id):
    """SSE stream for a single conversation thread — realtime with DB.

    Query params: platform (required) + account (optional, @-prefixed allowed).
    Pushes event `messages` with the full direct_messages array (last 100)
    whenever the thread changes. Polling-based for compatibility.
    """
    platform = request.args.get("platform")
    if platform not in {item.value for item in Platform}:
        return error("A supported conversation platform is required.")
    account = str(request.args.get("account", "")).strip().lstrip("@")
    query = {"source.client_username": scoped_client(), "user_id": user_id, "source.platform": platform}
    if account:
        query["source.account_username"] = account

    def generate():
        import hashlib

        last_hash = None
        heartbeat_counter = 0
        while True:
            try:
                conversation = db[USERS_COLLECTION].find_one(
                    query,
                    {"direct_messages": {"$slice": -100}, "_id": 0},
                )
                if not conversation:
                    yield f"event: error\ndata: {json.dumps({'message': 'Conversation not found.'})}\n\n"
                    time.sleep(5)
                    continue
                messages = conversation.get("direct_messages") or []
                payload = json_value(messages)
                # hash by length + last timestamp/text
                hash_input = str(len(messages))
                if messages:
                    last = messages[-1]
                    hash_input += f"|{last.get('timestamp')}|{last.get('text','')[:50]}|{last.get('role')}"
                cur_hash = hashlib.md5(hash_input.encode()).hexdigest()
                if cur_hash != last_hash:
                    last_hash = cur_hash
                    data = json.dumps(payload)
                    yield f"event: messages\ndata: {data}\n\n"
                    heartbeat_counter = 0
                else:
                    heartbeat_counter += 1
                    if heartbeat_counter % 10 == 0:
                        yield ": heartbeat\n\n"
                time.sleep(1.5)
            except GeneratorExit:
                break
            except Exception as exc:
                try:
                    yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
                except Exception:
                    pass
                time.sleep(3)

    return _sse_response(generate)


@api_bp.get("/analytics")
@api_auth()
def analytics():
    client = scoped_client()
    window = request.args.get("window", "M").upper()
    days = {"D": 1, "W": 7, "M": 30, "Y": 365}.get(window)
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else None

    account_filter = request.args.get("account", "").lstrip("@").strip()
    platform_filter = request.args.get("platform", "").strip().lower()

    def within(field):
        return {"$gte": [f"${field}", since]} if since else {"$literal": True}

    scope_match = {"source.client_username": client}
    if account_filter:
        scope_match["source.account_username"] = account_filter
    if platform_filter in {item.value for item in Platform}:
        scope_match["source.platform"] = platform_filter

    users_pipeline = [
        {"$match": scope_match},
        {"$group": {
            "_id": {"platform": "$source.platform", "account": "$source.account_username", "status": "$status"},
            "total": {"$sum": 1},
            "created": {"$sum": {"$cond": [within("created_at"), 1, 0]}},
            "updated": {"$sum": {"$cond": [within("updated_at"), 1, 0]}},
        }},
        {"$sort": {"_id.platform": ASCENDING, "_id.account": ASCENDING, "_id.status": ASCENDING}},
    ]
    users = [
        {
            "platform": item["_id"].get("platform") or "unknown",
            "account": item["_id"].get("account") or "unknown",
            "status": item["_id"].get("status") or "unknown",
            "total": item["total"],
            "created": item["created"],
            "updated": item["updated"],
        }
        for item in db[USERS_COLLECTION].aggregate(users_pipeline)
    ]

    messages_pipeline = [
        {"$match": scope_match},
        {"$unwind": "$direct_messages"},
        {"$match": {"direct_messages.timestamp": {"$type": "date"}}},
    ]
    if since:
        messages_pipeline.append({"$match": {"direct_messages.timestamp": {"$gte": since}}})
    messages_pipeline += [
        {"$group": {
            "_id": {
                "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$direct_messages.timestamp", "timezone": "Asia/Tehran"}},
                "role": "$direct_messages.role",
            },
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.day": ASCENDING, "_id.role": ASCENDING}},
    ]
    messages = [
        {"day": item["_id"]["day"], "role": item["_id"].get("role") or "unknown", "count": item["count"]}
        for item in db[USERS_COLLECTION].aggregate(messages_pipeline)
    ]

    new_users_pipeline = [
        {"$match": {**scope_match, "created_at": {"$type": "date"}}},
    ]
    if since:
        new_users_pipeline.append({"$match": {"created_at": {"$gte": since}}})
    new_users_pipeline += [
        {"$group": {
            "_id": {
                "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at", "timezone": "Asia/Tehran"}},
                "platform": "$source.platform",
            },
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.day": ASCENDING}},
    ]
    new_users = [
        {"day": item["_id"]["day"], "platform": item["_id"].get("platform") or "unknown", "count": item["count"]}
        for item in db[USERS_COLLECTION].aggregate(new_users_pipeline)
    ]
    return response({"window": window, "since": since, "users": users, "messages": messages, "new_users": new_users})


@api_bp.post("/broadcasts/telegram")
@api_auth()
@require_csrf
def telegram_broadcast():
    payload = body()
    text = payload.get("text")
    image_url = payload.get("image_url")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return error("Broadcast text is required and must be at most 4,000 characters.")
    if image_url is not None and (not isinstance(image_url, str) or not image_url.startswith("https://")):
        return error("Broadcast images must use an HTTPS URL.")
    result = TelegramService.broadcast_message(text.strip(), scoped_client(), image_url=image_url)
    # Normalize for frontend: frontend expects `matched`, service returns `total_users`
    if "matched" not in result and "total_users" in result:
        result["matched"] = result["total_users"]
    if "total_users" not in result and "matched" in result:
        result["total_users"] = result["matched"]
    return response(result)


@api_bp.post("/broadcasts/bale")
@api_auth()
@require_csrf
def bale_broadcast():
    payload = body()
    text = payload.get("text")
    image_url = payload.get("image_url")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return error("Broadcast text is required and must be at most 4,000 characters.")
    if image_url is not None and (not isinstance(image_url, str) or not image_url.startswith("https://")):
        return error("Broadcast images must use an HTTPS URL.")
    result = BaleService.broadcast_message(text.strip(), scoped_client(), image_url=image_url)
    if "matched" not in result and "total_users" in result:
        result["matched"] = result["total_users"]
    if "total_users" not in result and "matched" in result:
        result["total_users"] = result["matched"]
    return response(result)


def _custom_broadcast_send_one(platform, user_id, account_username, text, client_username, image_url=None):
    """Send a single broadcast message for custom broadcast, handling per-platform image logic.

    Returns message_id on success, None on failure. Never raises.
    """
    try:
        if platform == Platform.TELEGRAM.value:
            if image_url:
                # Re-use TelegramService logic for photo: try sendPhoto with correct token per account
                # Resolve token similarly to TelegramService.send_message but for photo
                import requests as _requests
                token = None
                if account_username:
                    normalized = str(account_username).lstrip("@")
                    for acc in Client.get_platform_accounts(client_username, Platform.TELEGRAM.value):
                        if (acc.get("username") or acc.get("bot_username")) == normalized:
                            token = acc.get("telegram_access_token")
                            break
                if not token:
                    creds = TelegramService.get_client_credentials(client_username)
                    token = creds.get('telegram_access_token') if creds else None
                if not token:
                    return None
                try:
                    url = f"https://api.telegram.org/bot{token}/sendPhoto"
                    payload = {"chat_id": user_id, "photo": image_url, "caption": text}
                    resp = _requests.post(url, json=payload, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get('ok'):
                        return data.get('result', {}).get('message_id')
                    return None
                except Exception:
                    return None
            return TelegramService.send_message(user_id, text, client_username, account_username=account_username)
        elif platform == Platform.BALE.value:
            if image_url:
                import requests as _requests
                from ..services.platforms.bale import BALE_API_BASE
                token = None
                if account_username:
                    normalized = str(account_username).lstrip("@")
                    for acc in Client.get_platform_accounts(client_username, Platform.BALE.value):
                        if (acc.get("username") or acc.get("bot_username")) == normalized:
                            token = acc.get("bale_access_token")
                            break
                if not token:
                    creds = BaleService.get_client_credentials(client_username)
                    token = creds.get('bale_access_token') if creds else None
                if not token:
                    return None
                try:
                    url = f"{BALE_API_BASE}/bot{token}/sendPhoto"
                    payload = {"chat_id": user_id, "photo": image_url, "caption": text}
                    resp = _requests.post(url, json=payload, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get('ok'):
                        return data.get('result', {}).get('message_id')
                    return None
                except Exception:
                    return None
            return BaleService.send_message(user_id, text, client_username, account_username=account_username)
        elif platform == Platform.INSTAGRAM.value:
            return InstagramService.send_message(user_id, text, client_username, account_username=account_username)
        else:
            return None
    except Exception as exc:  # defensive: never abort the broadcast loop
        logging.getLogger(__name__).warning(f"Broadcast send failed for {platform}:{user_id}: {exc}")
        return None


@api_bp.post("/broadcasts/custom")
@api_auth()
@require_csrf
def custom_broadcast():
    """Broadcast a message to conversations matching the supplied filters.

    Robust: per-recipient try/except so one failure never stops the blast.
    Resolves the exact bot account token via source.account_username, supports
    optional HTTPS image for Telegram/Bale, stores broadcast history, and
    returns matched/successful/failed for the UI.
    """
    payload = body()
    text = payload.get("text")
    image_url = payload.get("image_url")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return error("Broadcast text is required and must be at most 4,000 characters.")
    if image_url is not None and image_url != "":
        if not isinstance(image_url, str) or not image_url.startswith("https://"):
            return error("Broadcast images must use an HTTPS URL.")
        image_url = image_url.strip() or None
    else:
        image_url = None
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    query = conversation_filters(filters)
    text_clean = text.strip()
    now = datetime.now(timezone.utc)
    sent = {"successful": 0, "failed": 0, "matched": 0}
    # Projection must include account_username so we can resolve per-account tokens
    cursor = db[USERS_COLLECTION].find(query, {"user_id": 1, "source": 1})
    for conversation in cursor:
        sent["matched"] += 1
        platform = (conversation.get("source") or {}).get("platform")
        user_id = conversation.get("user_id")
        account_username = (conversation.get("source") or {}).get("account_username")
        # Basic guard: missing user_id -> count as failed and continue
        if not user_id or not platform:
            sent["failed"] += 1
            continue
        result = _custom_broadcast_send_one(platform, user_id, account_username, text_clean, scoped_client(), image_url=image_url)
        if not result:
            sent["failed"] += 1
            # Persist a failed broadcast marker so the thread/auditing shows the attempt
            # but never let storage failures abort the blast.
            try:
                failed_doc = {
                    "message_id": None,
                    "text": text_clean,
                    "role": MessageRole.BROADCAST.value,
                    "timestamp": now,
                    "broadcast_failed": True,
                    "broadcast_error": "platform_rejected",
                }
                if image_url:
                    failed_doc["media_url"] = image_url
                    failed_doc["media_type"] = "image"
                # Map platform to appropriate FAILED status; default to TELEGRAM_FAILED
                failed_status = {
                    Platform.TELEGRAM.value: UserStatus.TELEGRAM_FAILED.value,
                    Platform.BALE.value: getattr(UserStatus, "BALE_FAILED", UserStatus.TELEGRAM_FAILED).value,
                    Platform.INSTAGRAM.value: UserStatus.INSTAGRAM_FAILED.value,
                }.get(platform, UserStatus.TELEGRAM_FAILED.value)
                db[USERS_COLLECTION].update_one(
                    {"_id": conversation["_id"]},
                    {
                        "$push": {"direct_messages": failed_doc},
                        "$set": {"status": failed_status, "updated_at": now},
                    },
                )
            except Exception:
                pass
            continue
        sent["successful"] += 1
        try:
            doc = {
                "message_id": str(result),
                "text": text_clean,
                "role": MessageRole.BROADCAST.value,
                "timestamp": now,
            }
            if image_url:
                doc["media_url"] = image_url
                doc["media_type"] = "image"
            db[USERS_COLLECTION].update_one(
                {"_id": conversation["_id"]},
                {
                    "$push": {"direct_messages": doc},
                    "$set": {"status": UserStatus.BROADCASTED.value, "updated_at": now},
                },
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Failed to persist broadcast success for {user_id}: {exc}")
            # delivery succeeded even if persistence failed - keep successful count
            pass
    return response(sent)


def _sse_response(generator_fn):
    """Wrap a generator yielding SSE events into a Flask streaming Response."""
    return Response(
        stream_with_context(generator_fn()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _stream_ndjson_response(generator_fn):
    """Wrap a generator yielding ndjson lines into a Flask streaming Response."""
    return Response(
        stream_with_context(generator_fn()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@api_bp.post("/broadcasts/custom/stream")
@api_auth()
@require_csrf
def custom_broadcast_stream():
    """Streaming variant of custom broadcast: NDJSON progress events.

    Each line is a JSON object: {"type":"start"|"progress"|"done", ...}
    Frontend reads the stream via fetch+ReadableStream to render realtime progress.
    """
    payload = body()
    text = payload.get("text")
    image_url = payload.get("image_url")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return error("Broadcast text is required and must be at most 4,000 characters.")
    if image_url is not None and image_url != "":
        if not isinstance(image_url, str) or not image_url.startswith("https://"):
            return error("Broadcast images must use an HTTPS URL.")
        image_url = image_url.strip() or None
    else:
        image_url = None
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    query = conversation_filters(filters)
    text_clean = text.strip()
    client_username = scoped_client()

    # Count total upfront so the UI can show a determinate progress bar even
    # before the first delivery attempt.
    try:
        total = db[USERS_COLLECTION].count_documents(query)
    except Exception:
        total = 0

    def generate():
        now = datetime.now(timezone.utc)
        sent = {"successful": 0, "failed": 0}
        yield json.dumps({"type": "start", "total": total, "matched": total}) + "\n"
        if total == 0:
            yield json.dumps({"type": "done", "successful": 0, "failed": 0, "matched": 0, "total": 0}) + "\n"
            return
        try:
            cursor = db[USERS_COLLECTION].find(query, {"user_id": 1, "source": 1})
            processed = 0
            for conversation in cursor:
                processed += 1
                platform = (conversation.get("source") or {}).get("platform")
                user_id = conversation.get("user_id")
                account_username = (conversation.get("source") or {}).get("account_username")
                if not user_id or not platform:
                    sent["failed"] += 1
                else:
                    result = _custom_broadcast_send_one(platform, user_id, account_username, text_clean, client_username, image_url=image_url)
                    if not result:
                        sent["failed"] += 1
                        try:
                            failed_doc = {
                                "message_id": None,
                                "text": text_clean,
                                "role": MessageRole.BROADCAST.value,
                                "timestamp": now,
                                "broadcast_failed": True,
                                "broadcast_error": "platform_rejected",
                            }
                            if image_url:
                                failed_doc["media_url"] = image_url
                                failed_doc["media_type"] = "image"
                            failed_status = {
                                Platform.TELEGRAM.value: UserStatus.TELEGRAM_FAILED.value,
                                Platform.BALE.value: getattr(UserStatus, "BALE_FAILED", UserStatus.TELEGRAM_FAILED).value,
                                Platform.INSTAGRAM.value: UserStatus.INSTAGRAM_FAILED.value,
                            }.get(platform, UserStatus.TELEGRAM_FAILED.value)
                            db[USERS_COLLECTION].update_one(
                                {"_id": conversation["_id"]},
                                {"$push": {"direct_messages": failed_doc}, "$set": {"status": failed_status, "updated_at": now}},
                            )
                        except Exception:
                            pass
                    else:
                        sent["successful"] += 1
                        try:
                            doc = {
                                "message_id": str(result),
                                "text": text_clean,
                                "role": MessageRole.BROADCAST.value,
                                "timestamp": now,
                            }
                            if image_url:
                                doc["media_url"] = image_url
                                doc["media_type"] = "image"
                            db[USERS_COLLECTION].update_one(
                                {"_id": conversation["_id"]},
                                {"$push": {"direct_messages": doc}, "$set": {"status": UserStatus.BROADCASTED.value, "updated_at": now}},
                            )
                        except Exception:
                            pass
                percent = round(processed / total * 100) if total else 100
                yield json.dumps({
                    "type": "progress",
                    "current": processed,
                    "total": total,
                    "matched": total,
                    "successful": sent["successful"],
                    "failed": sent["failed"],
                    "percent": percent,
                }) + "\n"
                # Tiny cooperative yield so the WSGI server can flush each line
                # and avoid rate-limit hammering Telegram/Bale.
                if processed % 25 == 0:
                    time.sleep(0.05)
            yield json.dumps({
                "type": "done",
                "successful": sent["successful"],
                "failed": sent["failed"],
                "matched": total,
                "total": total,
            }) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return _stream_ndjson_response(generate)


@api_bp.post("/broadcasts/telegram/stream")
@api_auth()
@require_csrf
def telegram_broadcast_stream():
    """Streaming Telegram blast: NDJSON progress events for the Telegram-only audience."""
    payload = body()
    text = payload.get("text")
    image_url = payload.get("image_url")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return error("Broadcast text is required and must be at most 4,000 characters.")
    if image_url is not None and image_url != "":
        if not isinstance(image_url, str) or not image_url.startswith("https://"):
            return error("Broadcast images must use an HTTPS URL.")
        image_url = image_url.strip() or None
    else:
        image_url = None
    text_clean = text.strip()
    client_username = scoped_client()
    from ..models.user import User as UserModel

    try:
        users = UserModel.get_users_by_platform_for_client(platform="telegram", client_username=client_username)
    except Exception as exc:
        return error(f"Failed to retrieve Telegram users: {exc}", 500)

    total = len(users) if users else 0

    def generate():
        yield json.dumps({"type": "start", "total": total, "matched": total}) + "\n"
        if total == 0:
            yield json.dumps({"type": "done", "successful": 0, "failed": 0, "matched": 0, "total": 0}) + "\n"
            return
        successful = 0
        failed = 0
        # Re-use the per-user logic from TelegramService but yield progress.
        # We call _custom_broadcast_send_one for each telegram user so that
        # image handling + per-account token resolution is identical to the
        # non-streaming path and failures never abort the loop.
        for idx, user in enumerate(users):
            user_id = user.get("user_id")
            # Telegram users may be spread across multiple bot accounts; try to
            # find their account_username from DB if not present in the
            # lightweight projection.
            account_username = user.get("source", {}).get("account_username") if isinstance(user.get("source"), dict) else None
            if not account_username:
                try:
                    full = db[USERS_COLLECTION].find_one(
                        {"user_id": user_id, "source.client_username": client_username, "source.platform": "telegram"},
                        {"source.account_username": 1},
                    )
                    if full:
                        account_username = (full.get("source") or {}).get("account_username")
                except Exception:
                    pass
            res = _custom_broadcast_send_one(Platform.TELEGRAM.value, user_id, account_username, text_clean, client_username, image_url=image_url)
            # Persist broadcast history identically to the non-stream path
            now = datetime.now(timezone.utc)
            if res:
                successful += 1
                try:
                    doc = UserModel.create_message_document(text=text_clean, role=MessageRole.BROADCAST.value, media_type='image' if image_url else 'text', media_url=image_url)
                    # Ensure we use the same timestamp/message_id handling as _custom path
                    doc["message_id"] = str(res)
                    doc["timestamp"] = now
                    UserModel.add_direct_message(user_id, doc, client_username)
                    cur = UserModel.get_by_id(user_id, client_username)
                    if cur and cur.get('status') != UserStatus.WAITING.value:
                        UserModel.update_status(user_id, UserStatus.BROADCASTED.value, client_username)
                except Exception:
                    pass
            else:
                failed += 1
                try:
                    failed_doc = UserModel.create_message_document(text=f"[FAILED TO SEND] {text_clean}", role=MessageRole.BROADCAST.value, media_type='image' if image_url else 'text', media_url=image_url)
                    failed_doc["broadcast_failed"] = True
                    UserModel.add_direct_message(user_id, failed_doc, client_username)
                    UserModel.update_status(user_id, UserStatus.TELEGRAM_FAILED.value, client_username)
                except Exception:
                    pass
            yield json.dumps({
                "type": "progress",
                "current": idx + 1,
                "total": total,
                "matched": total,
                "successful": successful,
                "failed": failed,
                "percent": round((idx + 1) / total * 100) if total else 100,
            }) + "\n"
            if (idx + 1) % 50 == 0 and idx + 1 < total:
                time.sleep(1)
        yield json.dumps({"type": "done", "successful": successful, "failed": failed, "matched": total, "total": total}) + "\n"

    return _stream_ndjson_response(generate)


@api_bp.post("/broadcasts/bale/stream")
@api_auth()
@require_csrf
def bale_broadcast_stream():
    """Streaming Bale blast (mirrors Telegram streaming)."""
    payload = body()
    text = payload.get("text")
    image_url = payload.get("image_url")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return error("Broadcast text is required and must be at most 4,000 characters.")
    if image_url is not None and image_url != "":
        if not isinstance(image_url, str) or not image_url.startswith("https://"):
            return error("Broadcast images must use an HTTPS URL.")
        image_url = image_url.strip() or None
    else:
        image_url = None
    text_clean = text.strip()
    client_username = scoped_client()
    from ..models.user import User as UserModel

    try:
        users = UserModel.get_users_by_platform_for_client(platform="bale", client_username=client_username)
    except Exception as exc:
        return error(f"Failed to retrieve Bale users: {exc}", 500)
    total = len(users) if users else 0

    def generate():
        yield json.dumps({"type": "start", "total": total, "matched": total}) + "\n"
        if total == 0:
            yield json.dumps({"type": "done", "successful": 0, "failed": 0, "matched": 0, "total": 0}) + "\n"
            return
        successful = 0
        failed = 0
        for idx, user in enumerate(users):
            user_id = user.get("user_id")
            account_username = user.get("source", {}).get("account_username") if isinstance(user.get("source"), dict) else None
            if not account_username:
                try:
                    full = db[USERS_COLLECTION].find_one(
                        {"user_id": user_id, "source.client_username": client_username, "source.platform": "bale"},
                        {"source.account_username": 1},
                    )
                    if full:
                        account_username = (full.get("source") or {}).get("account_username")
                except Exception:
                    pass
            res = _custom_broadcast_send_one(Platform.BALE.value, user_id, account_username, text_clean, client_username, image_url=image_url)
            now = datetime.now(timezone.utc)
            if res:
                successful += 1
                try:
                    doc = UserModel.create_message_document(text=text_clean, role=MessageRole.BROADCAST.value, media_type='image' if image_url else 'text', media_url=image_url)
                    doc["message_id"] = str(res)
                    doc["timestamp"] = now
                    UserModel.add_direct_message(user_id, doc, client_username)
                    cur = UserModel.get_by_id(user_id, client_username)
                    if cur and cur.get('status') != UserStatus.WAITING.value:
                        UserModel.update_status(user_id, UserStatus.BROADCASTED.value, client_username)
                except Exception:
                    pass
            else:
                failed += 1
                try:
                    failed_doc = UserModel.create_message_document(text=f"[FAILED TO SEND] {text_clean}", role=MessageRole.BROADCAST.value, media_type='image' if image_url else 'text', media_url=image_url)
                    failed_doc["broadcast_failed"] = True
                    UserModel.add_direct_message(user_id, failed_doc, client_username)
                    failed_status = getattr(UserStatus, 'BALE_FAILED', UserStatus.TELEGRAM_FAILED).value
                    UserModel.update_status(user_id, failed_status, client_username)
                except Exception:
                    pass
            yield json.dumps({
                "type": "progress",
                "current": idx + 1,
                "total": total,
                "matched": total,
                "successful": successful,
                "failed": failed,
                "percent": round((idx + 1) / total * 100) if total else 100,
            }) + "\n"
            if (idx + 1) % 50 == 0 and idx + 1 < total:
                time.sleep(1)
        yield json.dumps({"type": "done", "successful": successful, "failed": failed, "matched": total, "total": total}) + "\n"

    return _stream_ndjson_response(generate)


@api_bp.get("/settings/workspace")
@api_auth()
def workspace_settings():
    client = Client.get_by_username(scoped_client())
    if not client:
        return error("Client not found.", 404, "not_found")
    result = client_summary(client)
    result["notes"] = client.get("notes", "")
    result["settings"] = client.get("settings", {})
    result["info"] = client.get("info", {})
    result["platforms"] = client.get("platforms", {})
    result["vector_store_ids"] = Client._normalize_vector_store_ids(client.get("keys", {}).get("vector_store_id"))
    return response(result)


@api_bp.patch("/settings/workspace")
@api_auth()
@require_csrf
def update_workspace_settings():
    payload = body()
    updates = {key: value for key, value in payload.items() if key in {"platforms", "notes", "settings", "info"}}
    if not updates:
        return error("No supported workspace fields were supplied.")
    if not Client.update(scoped_client(), updates):
        return error("Workspace settings could not be updated.", 400)
    load_main_app_globals_from_db()
    return response({"updated": True})


def _has_vision_model(client_username: str) -> bool:
    """Check if a vision model exists for the client in /root/hooshang/from_colab or fallbacks."""
    candidates = [
        f"/data/vision_models/{client_username}.pt",
        f"/root/hooshang/from_colab/{client_username}.pt",
        f"/root/cozmoz_application/from_colab/{client_username}.pt",
        f"/data/models/{client_username}.pt",
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return True
        except Exception:
            continue
    # Fallback: check any file in vision_models dir containing username
    for base in ["/data/vision_models", "/root/hooshang/from_colab", "/root/cozmoz_application/from_colab"]:
        try:
            if os.path.isdir(base):
                for fname in os.listdir(base):
                    if client_username in fname and fname.endswith(".pt"):
                        return True
        except Exception:
            continue
    return False


@api_bp.get("/settings/capabilities")
@api_auth()
def workspace_capabilities():
    """Return prerequisites for enabling modules: has_agents and has_vision_model."""
    client_username = scoped_client()
    agents = Client.get_agents(client_username)
    has_agents = len(agents) > 0
    has_vision = _has_vision_model(client_username)
    return response({"has_agents": has_agents, "has_vision_model": has_vision, "client_username": client_username})


@api_bp.get("/settings/accounts")
@api_auth()
def list_platform_accounts():
    platform = request.args.get("platform")
    if platform and platform not in {item.value for item in Platform}:
        return error("Invalid platform parameter.", 400)
    if platform:
        accounts = Client.get_platform_accounts(scoped_client(), platform=platform)
        return response(accounts)
    # Frontend expects grouped object {instagram:[], telegram:[], bale:[]} for overview/messages/agents filters
    client = Client.get_by_username(scoped_client())
    platforms = (client.get("platforms") or {}) if client else {}
    grouped = {
        "instagram": (platforms.get("instagram") or {}).get("accounts") or [],
        "telegram": (platforms.get("telegram") or {}).get("accounts") or [],
        "bale": (platforms.get("bale") or {}).get("accounts") or [],
    }
    return response(grouped)


@api_bp.post("/settings/accounts")
@api_auth()
@require_csrf
def add_platform_account():
    payload = body()
    platform = payload.get("platform")
    if platform not in {item.value for item in Platform}:
        return error("A valid platform ('instagram', 'telegram' or 'bale') is required.", 400)
    
    name = str(payload.get("name", "")).strip()
    if not name:
        return error("Account name/label is required.", 400)

    # Validate module prerequisites
    modules = payload.get("modules") or {}
    # DM AI Assistant and Orderbook require at least one agent
    if modules.get("dm_assist", {}).get("enabled") or modules.get("orderbook", {}).get("enabled"):
        agents = Client.get_agents(scoped_client())
        if not agents:
            return error("DM AI Assistant & Orderbook require an agent — create one in Agents first.", 400)
    # Vision AI requires a vision model file for this client
    if modules.get("vision", {}).get("enabled"):
        if not _has_vision_model(scoped_client()):
            return error(f"Vision AI requires a vision model for '{scoped_client()}' in /root/hooshang/from_colab/. Only Fixed Replies is available.", 400)

    account = Client.add_platform_account(scoped_client(), platform, payload)
    if not account:
        return error("Failed to create platform account.", 400)
    
    # If client requested immediate webhook configuration
    if payload.get("set_webhook_now"):
        if platform == Platform.TELEGRAM.value and account.get("telegram_access_token"):
            webhook_url = account.get("webhook_url") or f"{Config.BASE_URL}/telegram/{scoped_client()}/{account['id']}"
            if not account.get("webhook_url"):
                Client.update_platform_account(scoped_client(), account["id"], {"webhook_url": webhook_url})
                account["webhook_url"] = webhook_url
            ok, msg = TelegramService.set_webhook(
                account["telegram_access_token"],
                webhook_url,
                secret_token=account.get("secret_token")
            )
            if ok:
                verified, info = TelegramService.get_webhook_info(account["telegram_access_token"])
                bot_username = info.get("bot", {}).get("username")
                Client.update_platform_account(
                    scoped_client(),
                    account["id"],
                    {"webhook_verified": True, "bot_username": bot_username, "username": bot_username}
                )
                account["webhook_verified"] = True
                account["bot_username"] = bot_username
        elif platform == Platform.BALE.value and account.get("bale_access_token"):
            webhook_url = account.get("webhook_url") or f"{Config.BASE_URL}/bale/{scoped_client()}/{account['id']}"
            if not account.get("webhook_url"):
                Client.update_platform_account(scoped_client(), account["id"], {"webhook_url": webhook_url})
                account["webhook_url"] = webhook_url
            ok, msg = BaleService.set_webhook(
                account["bale_access_token"],
                webhook_url,
                secret_token=account.get("secret_token")
            )
            if ok:
                verified, info = BaleService.get_webhook_info(account["bale_access_token"])
                bot_username = info.get("bot", {}).get("username")
                Client.update_platform_account(
                    scoped_client(),
                    account["id"],
                    {"webhook_verified": True, "bot_username": bot_username, "username": bot_username}
                )
                account["webhook_verified"] = True
                account["bot_username"] = bot_username
        elif platform == Platform.INSTAGRAM.value and account.get("page_access_token"):
            ok, info = InstagramService.verify_credentials(account["page_access_token"], account.get("ig_id"))
            if ok:
                Client.update_platform_account(scoped_client(), account["id"], {"webhook_verified": True})
                account["webhook_verified"] = True

    load_main_app_globals_from_db()
    return response(account, 201)


@api_bp.patch("/settings/accounts/<account_id>")
@api_auth()
@require_csrf
def update_platform_account_route(account_id):
    payload = body()
    client_name = scoped_client()
    import logging
    logging.info(f"PATCH account {account_id} for client {client_name} with payload {payload}")
    # Validate module prerequisites if modules are being updated
    modules = payload.get("modules")
    if isinstance(modules, dict):
        if modules.get("dm_assist", {}).get("enabled") or modules.get("orderbook", {}).get("enabled"):
            agents = Client.get_agents(client_name)
            if not agents:
                return error("DM AI Assistant & Orderbook require an agent — create one in Agents first.", 400)
        if modules.get("vision", {}).get("enabled"):
            if not _has_vision_model(client_name):
                return error(f"Vision AI requires a vision model for '{client_name}' in /root/hooshang/from_colab/. Only Fixed Replies is available.", 400)
    if not Client.update_platform_account(client_name, account_id, payload):
        return error("Account not found or could not be updated.", 400)
    load_main_app_globals_from_db()
    return response({"updated": True})


@api_bp.delete("/settings/accounts/<account_id>")
@api_auth()
@require_csrf
def delete_platform_account(account_id):
    if not Client.delete_platform_account(scoped_client(), account_id):
        return error("Account not found or could not be deleted.", 404, "not_found")
    load_main_app_globals_from_db()
    return response({"deleted": True})


@api_bp.post("/settings/accounts/<account_id>/set-webhook")
@api_auth()
@require_csrf
def set_and_verify_webhook(account_id):
    client = Client.get_by_username(scoped_client())
    if not client:
        return error("Client not found.", 404)
    
    platforms = client.get("platforms", {}) or {}
    account = None
    platform = None
    for p_name, p_data in platforms.items():
        for acc in p_data.get("accounts", []):
            if acc.get("id") == account_id:
                account = acc
                platform = p_name
                break
        if account:
            break
    
    if not account:
        return error("Account not found.", 404)
    
    if platform == Platform.TELEGRAM.value:
        token = account.get("telegram_access_token")
        if not token:
            return error("Telegram Bot Token is missing for this account.", 400)
        webhook_url = account.get("webhook_url") or f"{Config.BASE_URL}/telegram/{scoped_client()}/{account_id}"
        secret_token = account.get("secret_token")
        
        ok, msg = TelegramService.set_webhook(token, webhook_url, secret_token=secret_token)
        if not ok:
            Client.update_platform_account(scoped_client(), account_id, {"webhook_verified": False})
            return error(f"Telegram returned an error: {msg}", 400)
        
        verified, info = TelegramService.get_webhook_info(token)
        bot_username = info.get("bot", {}).get("username")
        Client.update_platform_account(
            scoped_client(),
            account_id,
            {"webhook_verified": True, "bot_username": bot_username, "username": bot_username}
        )
        load_main_app_globals_from_db()
        return response({
            "success": True,
            "message": "Telegram webhook set and verified successfully.",
            "bot": info.get("bot"),
            "webhook": info.get("webhook"),
            "webhook_url": webhook_url
        })
    elif platform == Platform.BALE.value:
        token = account.get("bale_access_token")
        if not token:
            return error("Bale Bot Token is missing for this account.", 400)
        webhook_url = account.get("webhook_url") or f"{Config.BASE_URL}/bale/{scoped_client()}/{account_id}"
        secret_token = account.get("secret_token")
        ok, msg = BaleService.set_webhook(token, webhook_url, secret_token=secret_token)
        if not ok:
            Client.update_platform_account(scoped_client(), account_id, {"webhook_verified": False})
            return error(f"Bale returned an error: {msg}", 400)
        
        verified, info = BaleService.get_webhook_info(token)
        bot_username = info.get("bot", {}).get("username")
        Client.update_platform_account(
            scoped_client(),
            account_id,
            {"webhook_verified": True, "bot_username": bot_username, "username": bot_username}
        )
        load_main_app_globals_from_db()
        return response({
            "success": True,
            "message": "Bale webhook set and verified successfully.",
            "bot": info.get("bot"),
            "webhook": info.get("webhook"),
            "webhook_url": webhook_url
        })
    elif platform == Platform.INSTAGRAM.value:
        token = account.get("page_access_token")
        if not token:
            return error("Instagram Page Access Token is missing for this account.", 400)
        
        ok, info = InstagramService.verify_credentials(token, account.get("ig_id"))
        if not ok:
            Client.update_platform_account(scoped_client(), account_id, {"webhook_verified": False})
            return error(f"Instagram/Facebook Graph API returned an error: {info}", 400)
        
        Client.update_platform_account(scoped_client(), account_id, {"webhook_verified": True})
        load_main_app_globals_from_db()
        return response({
            "success": True,
            "message": "Instagram Page credentials and webhook configuration verified.",
            "page_info": info,
            "webhook_url": account.get("webhook_url") or f"{Config.BASE_URL}/instagram"
        })

    return error("Unsupported platform.", 400)


@api_bp.get("/system/clients")
@api_auth(system_admin=True)
def system_clients():
    params = page_params()
    if params is None:
        return error("Invalid pagination parameters.")
    page, limit = params
    total = db[CLIENTS_COLLECTION].count_documents({})
    clients = db[CLIENTS_COLLECTION].find().sort("username", ASCENDING).skip((page - 1) * limit).limit(limit)
    return response({"items": [client_summary(client) for client in clients], "page": page, "limit": limit, "total": total})


@api_bp.post("/system/clients")
@api_auth(system_admin=True)
@require_csrf
def system_create_client():
    payload = body()
    username = str(payload.get("username", "")).strip()
    business_name = str(payload.get("business_name", "")).strip()
    password = payload.get("password")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", username) or not business_name:
        return error("Username must be 3-64 letters, numbers, underscores, or hyphens; business name is required.")
    if not isinstance(password, str) or len(password) < 12:
        return error("An initial password of at least 12 characters is required.")
    created = Client.create(
        username,
        business_name,
        status=payload.get("status", ClientStatus.INACTIVE.value),
        password=password,
        is_admin=True,
        email=payload.get("email"),
    )
    if not created:
        return error("Client could not be created. It may already exist.", 409, "conflict")
    return response(client_summary(created), 201)


@api_bp.put("/system/clients/<username>/credentials")
@api_auth(system_admin=True)
@require_csrf
def replace_client_credentials(username):
    payload = body()
    credentials = {key: value for key, value in payload.items() if key in SECRET_FIELDS - {"password"} and isinstance(value, str)}
    if not credentials:
        return error("At least one supported credential is required.")
    if not Client.get_by_username(username):
        return error("Client not found.", 404, "not_found")
    db[CLIENTS_COLLECTION].update_one(
        {"username": username},
        {"$set": {f"keys.{key}": value for key, value in credentials.items()}},
    )
    load_main_app_globals_from_db()
    return response({"updated": True})


@api_bp.post("/system/clients/<username>/telegram-webhook")
@api_auth(system_admin=True)
@require_csrf
def configure_telegram_webhook(username):
    """System-admin alias for configuring Telegram webhooks.

    Delegates to the per-account flow: every Telegram account of the client gets
    its own account-scoped webhook URL (same as the Connect page 'Verify Webhook').
    """
    if not Config.BASE_URL.startswith("https://"):
        return error("BASE_URL must be a trusted HTTPS public origin before configuring webhooks.", 409, "invalid_configuration")
    accounts = Client.get_platform_accounts(username, Platform.TELEGRAM.value)
    if accounts:
        results = []
        for acc in accounts:
            token = acc.get("telegram_access_token")
            if not token:
                results.append({"account_id": acc.get("id"), "ok": False, "error": "missing_token"})
                continue
            url = acc.get("webhook_url") or f"{Config.BASE_URL.rstrip('/')}/telegram/{username}/{acc.get('id')}"
            ok, msg = TelegramService.set_webhook(token, url, secret_token=acc.get("secret_token"))
            if ok and not acc.get("webhook_url"):
                Client.update_platform_account(username, acc.get("id"), {"webhook_url": url})
            results.append({"account_id": acc.get("id"), "ok": ok, "url": url, **({"error": msg} if not ok else {})})
        all_ok = all(r.get("ok") for r in results)
        return response({"configured": all_ok, "results": results}, 200 if all_ok else 502)
    # Legacy: client-level token only
    credentials = TelegramService.get_client_credentials(username)
    token = credentials.get("telegram_access_token") if credentials else None
    if not token:
        return error("This client has no Telegram bot credential.", 400)
    ok, msg = TelegramService.set_webhook(token, f"{Config.BASE_URL.rstrip('/')}/telegram/{username}")
    if not ok:
        return error("Telegram rejected the webhook configuration.", 502, "platform_rejected")
    return response({"configured": True})


@api_bp.get("/system/clients/<username>/telegram-webhook")
@api_auth(system_admin=True)
def telegram_webhook_info(username):
    credentials = TelegramService.get_client_credentials(username)
    token = credentials.get("telegram_access_token") if credentials else None
    if not token:
        return error("This client has no Telegram bot credential.", 400)
    import requests

    result = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=20)
    data = result.json() if result.content else {}
    if not result.ok or not data.get("ok"):
        return error("Telegram rejected the webhook information request.", 502, "platform_rejected")
    return response(data.get("result", {}))


@api_bp.delete("/system/clients/<username>/telegram-webhook")
@api_auth(system_admin=True)
@require_csrf
def delete_telegram_webhook(username):
    credentials = TelegramService.get_client_credentials(username)
    token = credentials.get("telegram_access_token") if credentials else None
    if not token:
        return error("This client has no Telegram bot credential.", 400)
    import requests

    result = requests.post(
        f"https://api.telegram.org/bot{token}/deleteWebhook",
        json={"drop_pending_updates": bool(body().get("drop_pending_updates", False))},
        timeout=20,
    )
    data = result.json() if result.content else {}
    if not result.ok or not data.get("ok"):
        return error("Telegram rejected the webhook deletion.", 502, "platform_rejected")
    return response({"deleted": True})
