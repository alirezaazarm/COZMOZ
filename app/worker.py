"""Singleton scheduler process for background message processing."""

import logging

from apscheduler.triggers.interval import IntervalTrigger

# The worker never imports main.py, so without this all job/mediator INFO logs
# are silently dropped (root logger defaults to WARNING).
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

from .jobs.message_job import process_messages_job
from .jobs.scheduler import scheduler, shutdown_hook, start_scheduler
from .jobs.status_recovery_job import recover_failed_assistant_status_job
from .utils.helpers import load_main_app_globals_from_db


def run() -> None:
    load_main_app_globals_from_db()
    start_scheduler()
    scheduler.add_job(
        process_messages_job,
        IntervalTrigger(seconds=30),
        id="process_messages",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=120,
        coalesce=True,
    )
    scheduler.add_job(
        recover_failed_assistant_status_job,
        IntervalTrigger(minutes=2),
        id="status_recovery",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
        coalesce=True,
    )
    try:
        import time
        while True:
            time.sleep(60)
    finally:
        shutdown_hook()


if __name__ == "__main__":
    run()
