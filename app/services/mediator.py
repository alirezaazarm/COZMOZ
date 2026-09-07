from .AI.openai_service import OpenAIService
from .platforms.instagram import InstagramService
from .platforms.telegram import TelegramService
from .platforms.bale import BaleService
from .message_service import MessageService
from ..models.enums import UserStatus, MessageRole, ModuleType, Platform
from ..models.client import Client
from ..utils.helpers import get_app_settings
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Mediator:
    def __init__(self, db, client_username):
        self.db = db
        self.client_username = client_username
        self.openai_service = OpenAIService(client_username=client_username)
        self.message_service = MessageService(db, client_username)
        self._agents_cache = None

    def _with_account(self, account_username):
        """Rebind the message service to a specific account scope (same user_id can exist per account)."""
        if self.message_service.account_username != account_username:
            self.message_service = MessageService(self.db, self.client_username, account_username=account_username)

    def _get_agent_for_account(self, account_username=None, platform=None):
        """Return the first active agent bound to this account (account_id match);
        if none is bound to the account, fall back to any active agent for the platform."""
        if self._agents_cache is None:
            try:
                self._agents_cache = Client.get_agents(self.client_username) or []
            except Exception:
                self._agents_cache = []
        agents = [a for a in self._agents_cache if a.get("status", "active") == "active"]
        if platform:
            agents = [a for a in agents if a.get("platform") in (None, "", platform.value if hasattr(platform, 'value') else platform)]
        if account_username:
            normalized = str(account_username).lstrip("@")
            # Try to map the account username to its account id, then match agent.account_id
            account_id = None
            try:
                for acc in Client.get_platform_accounts(self.client_username, platform.value if hasattr(platform, 'value') else platform):
                    if (acc.get("username") or acc.get("bot_username") or acc.get("id")) == normalized:
                        account_id = acc.get("id")
                        break
            except Exception:
                pass
            for a in agents:
                if a.get("account_id") and a.get("account_id") == account_id:
                    return a
                if a.get("account_id") and (a.get("account_id") == normalized):
                    return a
            # fall through to platform-level fallback
        # No account-specific agent: first active platform agent without account binding, else first active
        unbound = [a for a in agents if not a.get("account_id")]
        return unbound[0] if unbound else (agents[0] if agents else None)

    def process_pending_messages(self, cutoff_time=None, platform=None, account_username=None):
        platform_log = f" for platform: {platform.value} account: @{account_username}" if platform else ""
        logger.info(f"Starting message processing cycle for client: {self.client_username}{platform_log}")

        # Check if assistant is disabled in app settings (client-specific)
        app_settings = get_app_settings(self.client_username)
        if not app_settings.get(ModuleType.DM_ASSIST.value, True):
            logger.info(f"Assistant is disabled in app settings for client {self.client_username}. Skipping message processing.")
            return

        # Get all users with WAITING status that have messages (scoped to client+platform+account)
        users_waiting = self._get_waiting_users(cutoff_time, platform, account_username=account_username)
        logger.info(f"Found {len(users_waiting)} users with WAITING status for client {self.client_username}{platform_log}")

        for user_id, doc_id in users_waiting:
            try:
                # Process each user's messages with this account's agent (if any)
                self._with_account(account_username)
                agent = self._get_agent_for_account(account_username=account_username, platform=platform)
                if platform:
                    logger.info(f"Using agent {(agent or {}).get('id') or 'client-default'} for @{account_username} on {platform.value}")
                    self.openai_service.agent = agent
                self._process_user_messages(user_id, cutoff_time, account_username=account_username, doc_id=doc_id)
            except Exception as user_error:
                logger.error(f"Failed processing user {user_id} for client {self.client_username} (account: @{account_username}): {str(user_error)}", exc_info=True)
                # Update user status to indicate failure
                self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
                continue

    def _get_waiting_users(self, cutoff_time=None, platform=None, account_username=None):
        platform_log = f" and platform {platform.value} account @{account_username}" if platform else ""
        logger.info(f"Getting users with WAITING status and messages older than {cutoff_time} for client {self.client_username}{platform_log}")

        # Make sure cutoff_time is timezone-aware if it's not None
        if cutoff_time is not None and cutoff_time.tzinfo is None:
            cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

        # New schema documents are fully scoped via source.*; match both
        match_condition = {
            "status": UserStatus.WAITING.value,
            "$or": [
                {"source.client_username": self.client_username},
                {"client_username": self.client_username, "source": {"$exists": False}},
            ],
        }

        # Add platform to match condition if provided (support both schemas)
        if platform:
            match_condition["$and"] = match_condition.get("$and", []) + [
                {"$or": [{"source.platform": platform.value}, {"platform": platform.value, "source.platform": {"$exists": False}}]}
            ]

        # Scope to a specific account when provided
        if account_username:
            match_condition.setdefault("$and", []).append(
                {"$or": [
                    {"source.account_username": account_username},
                    {"account_username": account_username},
                ]}
            )

        # Build the aggregation pipeline
        pipeline = [{"$match": match_condition}]

        # Add additional match condition if cutoff_time is provided
        # Find users whose LATEST message is older than the cutoff time
        if cutoff_time is not None:
            pipeline.extend([
                {"$match": {"direct_messages": {"$exists": True, "$ne": []}}},
                {"$unwind": "$direct_messages"},
                {"$match": {"direct_messages.role": MessageRole.USER.value}},
                # Group by document _id, NOT user_id: the same platform user can
                # have one doc per (client, platform, account) and each must be
                # processed independently with its own bot.
                {"$group": {
                    "_id": "$_id",
                    "latest_msg_time": {"$max": "$direct_messages.timestamp"},
                    "user_id": {"$first": "$user_id"}
                }},
                {"$match": {"latest_msg_time": {"$lte": cutoff_time}}}
            ])
        
        pipeline.append({"$project": {"user_id": 1, "_id": 1}})

        users = list(self.db.users.aggregate(pipeline))
        results = [(user.get('user_id'), user.get('_id')) for user in users]

        logger.info(f"Found {len(results)} user documents with WAITING status and latest message older than cutoff for client {self.client_username}{platform_log}")
        return results

    def _account_scoped_user_find(self, user_id, account_username, platform=None):
        """Find the user doc scoped to client + (optional) platform + (optional) account."""
        clauses = [
            {"source.client_username": self.client_username},
            {"client_username": self.client_username, "source": {"$exists": False}},
        ]
        or_clause = [{"$or": clauses}]
        matches = []
        base = {"user_id": user_id, **or_clause[0]}
        if platform:
            base["$and"] = [{"$or": [{"source.platform": platform.value}, {"platform": platform.value}]}]
        if account_username:
            base.setdefault("$and", []).append(
                {"$or": [{"source.account_username": account_username}, {"account_username": account_username}]}
            )
        return self.db.users.find_one(base), base

    def _process_user_messages(self, user_id, cutoff_time=None, account_username=None, doc_id=None):
        logger.info(f"Processing batch messages for user {user_id} (client: {self.client_username}, account: @{account_username}, doc: {doc_id})")

        try:
            # Get the exact user document by _id when known (source is part of identity);
            # otherwise fall back to the client+account-scoped lookup.
            if doc_id is not None:
                user = self.db.users.find_one({"_id": doc_id})
                user_query = {"_id": doc_id}
            else:
                user, user_query = self._account_scoped_user_find(user_id, account_username, platform=None)
            if not user:
                logger.warning(f"User {user_id} not found for client {self.client_username} account @{account_username}")
                return

            # Ensure cutoff_time is properly timezone-aware if provided (for logging only)
            if cutoff_time is not None and cutoff_time.tzinfo is None:
                cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

            # Get all user messages since the last assistant/admin reply as a single batch
            user_messages = self.message_service.get_user_messages(user_id, cutoff_time)
            if not user_messages:
                logger.info(f"No user messages found for user {user_id} (client: {self.client_username})")
                return

            # Get the message texts for processing
            message_texts = [msg.get('text') for msg in user_messages]
            logger.info(f"Processing batch of {len(user_messages)} user messages: {message_texts} (client: {self.client_username})")

            # Process with OpenAI (client-specific; persist thread state on THIS document)
            previous_response_id = self.openai_service.ensure_thread(user)
            doc_query = {"_id": user["_id"]} if user.get("_id") is not None else user_query
            response_text = self.openai_service.process_messages(
                previous_response_id,
                message_texts,
                user_id=user_id,
                user_query=doc_query,
            )

            if not response_text:
                logger.warning(f"No response generated for user {user_id} (client: {self.client_username})")
                self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
                return

            logger.info(f"Generated response: {response_text} (client: {self.client_username}, account: @{account_username})")

            # Determine platform (prefer nested source, fall back to legacy top-level)
            source_doc = user.get("source") or {}
            platform_value = source_doc.get("platform") or user.get("platform")
            # Build an update query that targets exactly this user document
            update_query = {"_id": user["_id"]} if user.get("_id") is not None else user_query

            try:
                if platform_value == Platform.INSTAGRAM.value:
                    mids = InstagramService.send_message(user_id, response_text, client_username=self.client_username, account_username=account_username)

                    if mids:
                        if isinstance(mids, list):
                            for i, mid in enumerate(mids):
                                if i == 0:
                                    message_doc = {
                                        "text": response_text,
                                        "role": MessageRole.ASSISTANT.value,
                                        "timestamp": datetime.now(timezone.utc),
                                        "mid": mid
                                    }
                                else:
                                    message_doc = {
                                        "text": f"[Part {i+1} of assistant response]",
                                        "role": MessageRole.ASSISTANT.value,
                                        "timestamp": datetime.now(timezone.utc),
                                        "mid": mid
                                    }
                                self.db.users.update_one(
                                    update_query,
                                    {"$push": {"direct_messages": message_doc}}
                                )
                        else:
                            message_doc = {
                                "text": response_text,
                                "role": MessageRole.ASSISTANT.value,
                                "timestamp": datetime.now(timezone.utc),
                                "mid": mids
                            }
                            self.db.users.update_one(
                                update_query,
                                {"$push": {"direct_messages": message_doc}}
                            )
                        self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_REPLIED.value)
                        logger.info(f"Successfully sent and stored assistant response for IG user {user_id} (client: {self.client_username}, account: @{account_username})")
                    else:
                        self.message_service.update_user_status(user_id, UserStatus.INSTAGRAM_FAILED.value)
                elif platform_value == Platform.TELEGRAM.value:
                    message_id = TelegramService.send_message(chat_id=user_id, text=response_text, client_username=self.client_username, account_username=account_username)
                    if message_id:
                        message_doc = {
                            "text": response_text,
                            "role": MessageRole.ASSISTANT.value,
                            "timestamp": datetime.now(timezone.utc),
                            "mid": message_id
                        }
                        self.db.users.update_one(
                            update_query,
                            {"$push": {"direct_messages": message_doc}}
                        )
                        self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_REPLIED.value)
                        logger.info(f"Successfully sent and stored assistant response for TG user {user_id} (client: {self.client_username}, account: @{account_username})")
                    else:
                        self.message_service.update_user_status(user_id, UserStatus.TELEGRAM_FAILED.value)
                elif platform_value == Platform.BALE.value:
                    message_id = BaleService.send_message(chat_id=user_id, text=response_text, client_username=self.client_username, account_username=account_username)
                    if message_id:
                        message_doc = {
                            "text": response_text,
                            "role": MessageRole.ASSISTANT.value,
                            "timestamp": datetime.now(timezone.utc),
                            "mid": message_id
                        }
                        self.db.users.update_one(
                            update_query,
                            {"$push": {"direct_messages": message_doc}}
                        )
                        self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_REPLIED.value)
                        logger.info(f"Successfully sent and stored assistant response for Bale user {user_id} (client: {self.client_username}, account: @{account_username})")
                    else:
                        failed_status = getattr(UserStatus, "BALE_FAILED", UserStatus.TELEGRAM_FAILED).value
                        self.message_service.update_user_status(user_id, failed_status)
                else:
                    logger.error(f"Unknown or unsupported platform '{platform_value}' for user {user_id}")
                    self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)

            except Exception as insta_error:
                logger.error(f"Message send failed for client {self.client_username} (account: @{account_username}): {str(insta_error)}")
                # Set platform-specific failure when possible
                platform_value = (user.get("source") or {}).get("platform") or user.get("platform")
                if platform_value == Platform.TELEGRAM.value:
                    self.message_service.update_user_status(user_id, UserStatus.TELEGRAM_FAILED.value)
                elif platform_value == Platform.INSTAGRAM.value:
                    self.message_service.update_user_status(user_id, UserStatus.INSTAGRAM_FAILED.value)
                else:
                    self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
                raise

        except Exception as e:
            logger.error(f"Processing failed for user {user_id} (client: {self.client_username}): {str(e)}", exc_info=True)
            self.message_service.update_user_status(user_id, UserStatus.ASSISTANT_FAILED.value)
            raise
