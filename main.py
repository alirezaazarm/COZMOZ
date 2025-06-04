from flask import Flask
from apscheduler.triggers.interval import IntervalTrigger
from app.jobs.scheduler import scheduler, start_scheduler, shutdown_hook
from app.jobs.message_job import process_messages_job
from app.jobs.post_story_job import fetch_posts_job, fetch_stories_job
from app.jobs.status_recovery_job import recover_failed_assistant_status_job
from app.routes.webhook import webhook_bp
from app.routes.update import update_bp
import logging

logging.basicConfig(
    handlers=[logging.FileHandler('logs.txt', encoding='utf-8'), logging.StreamHandler()],
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1200 * 1024 * 1024
app.register_blueprint(webhook_bp)
app.register_blueprint(update_bp)

if __name__ == '__main__':
    try:
        start_scheduler()

        scheduler.remove_all_jobs()

        scheduler.add_job(
            process_messages_job,
            IntervalTrigger(seconds=30),
            max_instances=1,
            misfire_grace_time=120,
            coalesce=True
        )

        scheduler.add_job(
            recover_failed_assistant_status_job,
            IntervalTrigger(minutes=2),
            id='status_recovery_job',
            max_instances=1,
            misfire_grace_time=60,
            coalesce=True
        )

#        scheduler.add_job(
 #           fetch_posts_job,
  #          IntervalTrigger(minutes=30),
   #         id='fetch_posts_job',
    #        max_instances=1,
     #       misfire_grace_time=300,
      #      coalesce=True
       # )

#        scheduler.add_job(
 #           fetch_stories_job,
  #          IntervalTrigger(minutes=6),
   #         id='fetch_stories_job',
    #        max_instances=1,
     #       misfire_grace_time=120,
      #      coalesce=True
       # )

        app.run(host='localhost', port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        shutdown_hook()
    except Exception as e:
        logging.critical(f"Failed to start: {str(e)}")
        shutdown_hook()