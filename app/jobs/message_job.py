from ..services.mediator import Mediator
from ..utils.helpers import get_db
from ..config import Config
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime, timezone, timedelta
import logging
from ..models.client import Client
from ..models.enums import ModuleType, Platform

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=10))
def process_messages_job():
    logger.info("Starting message processing job")
    try:
        # Get all active clients
        active_clients = Client.get_all_active()
        if not active_clients:
            logger.info("No active clients found. Skipping message processing job.")
            return

        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=Config.BATCH_WINDOW_SECONDS)
        logger.info(f"Processing messages older than {cutoff_time} (BATCH_WINDOW={Config.BATCH_WINDOW_SECONDS}s)")

        for client in active_clients:
            client_username = client.get('username')
            platforms_cfg = client.get("platforms", {}) or {}

            def account_dm_assist_enabled(platform_key, account):
                """DM Assist check, per account first, then platform-level fallback."""
                acc_enabled = (account.get("modules") or {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled")
                if acc_enabled is None:
                    acc_enabled = platforms_cfg.get(platform_key, {}).get('modules', {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled", False)
                return bool(acc_enabled) and account.get("status", "active") == "active"

            # Legacy platform-level flags (used when a platform has no accounts)
            telegram_dm_assist_enabled = platforms_cfg.get("telegram", {}).get('modules', {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled", False)
            instagram_dm_assist_enabled = platforms_cfg.get("instagram", {}).get('modules', {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled", False)
            bale_dm_assist_enabled = platforms_cfg.get("bale", {}).get('modules', {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled", False)

            if not telegram_dm_assist_enabled and not instagram_dm_assist_enabled and not bale_dm_assist_enabled:
                has_any_account_assist = any(
                    (acc.get("modules") or {}).get(ModuleType.DM_ASSIST.value, {}).get("enabled")
                    for pdata in platforms_cfg.values() for acc in (pdata.get("accounts") or [])
                )
                if not has_any_account_assist:
                    logger.info(f"DM Assist is disabled for all platforms for client '{client_username}'. Skipping.")
                    continue

            with get_db() as db:
                mediator = Mediator(db, client_username=client_username)

                for platform in (Platform.TELEGRAM, Platform.INSTAGRAM, Platform.BALE):
                    pdata = platforms_cfg.get(platform.value, {}) or {}
                    accounts = pdata.get("accounts") or []
                    if accounts:
                        # Per-account processing: only accounts whose own modules.dm_assist is enabled
                        for account in accounts:
                            account_username = account.get("username") or account.get("bot_username") or account.get("id")
                            if not account_username:
                                continue
                            if not account_dm_assist_enabled(platform.value, account):
                                logger.info(f"DM Assist disabled for client '{client_username}' platform {platform.value} account @{account_username}. Skipping this account.")
                                continue
                            logger.info(f"DM Assist enabled for client '{client_username}' platform {platform.value} account @{account_username}. Processing pending messages.")
                            mediator.process_pending_messages(cutoff_time, platform=platform, account_username=account_username)
                    else:
                        # Legacy: no accounts configured -> platform-level processing (no account filter)
                        legacy_enabled = {
                            Platform.TELEGRAM: telegram_dm_assist_enabled,
                            Platform.INSTAGRAM: instagram_dm_assist_enabled,
                            Platform.BALE: bale_dm_assist_enabled,
                        }[platform]
                        if legacy_enabled:
                            logger.info(f"DM Assist is enabled (platform-level, no accounts) for client '{client_username}' on {platform.value}. Processing pending messages.")
                            mediator.process_pending_messages(cutoff_time, platform=platform)
                        else:
                            logger.info(f"DM Assist is disabled for client '{client_username}' on {platform.value}. Skipping.")

    except Exception as job_error:
        logger.critical(f"Job failed: {str(job_error)}", exc_info=True)
        raise
    finally:
        logger.info("Completed processing cycle")