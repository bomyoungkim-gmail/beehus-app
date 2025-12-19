"""
Celery Beat Scheduler - Sync periodic jobs from MongoDB
"""
from celery import Celery
from celery.schedules import crontab
from core.models.mongo_models import Job
import asyncio


def get_beat_schedule():
    """
    Dynamic schedule loader for Celery Beat.
    Reads Job documents with schedule field and creates Celery Beat tasks.
    """
    async def _get_jobs():
        from core.db import init_db
        await init_db()
        
        # Get all active jobs with schedules
        jobs = await Job.find(
            Job.status == "active",
            Job.schedule != None,
            Job.schedule != ""
        ).to_list()
        
        schedule = {}
        for job in jobs:
            # Parse cron expression (e.g., "*/5 * * * *" = every 5 minutes)
            # Simple format: "minute hour day month day_of_week"
            parts = job.schedule.split()
            if len(parts) == 5:
                schedule[f'job-{job.id}'] = {
                    'task': 'core.tasks.scheduled_job_runner',
                    'schedule': crontab(
                        minute=parts[0],
                        hour=parts[1],
                        day_of_month=parts[2],
                        month_of_year=parts[3],
                        day_of_week=parts[4]
                    ),
                    'args': (str(job.id),)
                }
        
        return schedule
    
    # Run async function synchronously
    return asyncio.run(_get_jobs())
