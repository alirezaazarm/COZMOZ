from flask import Flask
from apscheduler.triggers.interval import IntervalTrigger
from app.models.base import engine, Base
from app.jobs.scheduler import scheduler, start_scheduler, shutdown_hook
from app.jobs.message_job import process_messages_job, cleanup_processed_messages
from app.routes.webhook import webhook_bp
from app.routes.update import update_bp
import logging

logging.basicConfig(
    handlers=[logging.FileHandler('logs.txt', encoding='utf-8'), logging.StreamHandler()],
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1200 * 1024 * 1024
app.register_blueprint(webhook_bp)
app.register_blueprint(update_bp)

if __name__ == '__main__':
    try:
        Base.metadata.create_all(bind=engine)

        start_scheduler()

        scheduler.add_job(
            process_messages_job,
            IntervalTrigger(seconds=30),
            max_instances=1,
            misfire_grace_time=120,
            coalesce=True
        )
        scheduler.add_job(
            cleanup_processed_messages,
            IntervalTrigger(hours=1),
            misfire_grace_time=300,
            coalesce=True
        )

        app.run(host='localhost', port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        shutdown_hook()
    except Exception as e:
        logging.critical(f"Failed to start: {str(e)}")
        shutdown_hook()