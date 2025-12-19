from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_config.settings')

app = Celery('beehus')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in core module
app.autodiscover_tasks(['core'])

# Celery Beat configuration
app.conf.beat_schedule_filename = '/app/celerybeat-schedule'

@app.task(bind=True)
def debug_task(self):
    """Simple debug task for testing Celery"""
    print(f'Request: {self.request!r}')
    return 'Debug task completed'

# Dynamic Beat Schedule Loader
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """
    Load periodic tasks from MongoDB on Celery Beat startup.
    Runs every 60 seconds to sync new jobs.
    """
    from core.beat_schedule import get_beat_schedule
    
    # Reload schedule every minute to pick up new jobs
    sender.add_periodic_task(60.0, sync_beat_schedule.s(), name='sync-beat-schedule')
    
    # Load initial schedule
    schedule = get_beat_schedule()
    for name, config in schedule.items():
        sender.add_periodic_task(
            config['schedule'],
            sender.tasks[config['task']].s(*config['args']),
            name=name
        )

@app.task
def sync_beat_schedule():
    """Sync schedule from MongoDB (called every minute)"""
    from core.beat_schedule import get_beat_schedule
    schedule = get_beat_schedule()
    return f"Synced {len(schedule)} scheduled jobs"
