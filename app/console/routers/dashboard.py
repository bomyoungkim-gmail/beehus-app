"""
Dashboard Router - API endpoints for dashboard statistics and recent runs.
"""

import logging
from datetime import timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter

from core.models.mongo_models import Job, Run
from core.utils.date_utils import get_now
from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats():
    """
    Get dashboard statistics from real database.
    Uses a single aggregation pipeline to avoid multiple round-trips.
    """
    now = get_now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    pipeline = [
        {
            "$facet": {
                "by_status": [
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}}
                ],
                "recent_success": [
                    {"$match": {"status": "success", "created_at": {"$gte": week_ago}}},
                    {"$count": "n"},
                ],
                "previous_success": [
                    {"$match": {"status": "success", "created_at": {"$gte": two_weeks_ago, "$lt": week_ago}}},
                    {"$count": "n"},
                ],
            }
        }
    ]

    result = await Run.get_motor_collection().aggregate(pipeline).to_list(length=1)
    facet = result[0] if result else {}

    status_map: dict[str, int] = {}
    for item in facet.get("by_status", []):
        status_map[item["_id"]] = item["count"]

    successful_runs = status_map.get("success", 0)
    failed_runs = status_map.get("failed", 0)
    running_runs = status_map.get("running", 0)
    queued_runs = status_map.get("queued", 0)

    recent_success = facet["recent_success"][0]["n"] if facet.get("recent_success") else 0
    previous_success = facet["previous_success"][0]["n"] if facet.get("previous_success") else 0

    success_trend = 0.0
    if previous_success > 0:
        success_trend = round(((recent_success - previous_success) / previous_success) * 100, 1)

    active_total = running_runs + queued_runs
    active_jobs = await Job.find(Job.status == "active").count()

    return {
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "running_runs": running_runs,
        "queued_runs": queued_runs,
        "active_workers": active_total,
        "browser_sessions": running_runs,
        "success_trend": success_trend,
        "total_runs": sum(status_map.values()),
        "active_jobs": active_jobs,
    }


@router.get("/recent-runs")
async def get_recent_runs(limit: int = 10):
    """
    Get recent runs with job details for dashboard table.
    Batch-fetches missing job metadata to avoid N+1 queries.
    """
    runs = await Run.find().sort(-Run.created_at).limit(limit).to_list()

    # Collect job_ids that need a DB lookup (missing connector or job_name)
    missing_job_ids = {
        str(run.job_id)
        for run in runs
        if run.job_id and run.job_id != "test-job" and (not run.connector or not run.job_name)
    }

    # Single batch query instead of one query per run
    job_cache: dict[str, Job] = {}
    if missing_job_ids:
        fetched_jobs = await Job.find(
            {"_id": {"$in": list(missing_job_ids)}}
        ).to_list()
        job_cache = {str(j.id): j for j in fetched_jobs}

    local_tz = ZoneInfo(settings.TIMEZONE)

    result = []
    for run in runs:
        connector_name = run.connector or "Unknown"
        job_name = run.job_name

        if (not run.connector or not job_name) and run.job_id and run.job_id != "test-job":
            cached_job = job_cache.get(str(run.job_id))
            if cached_job:
                if not run.connector:
                    connector_name = cached_job.connector
                if not job_name:
                    job_name = cached_job.name

        created_at_str = None
        if run.created_at:
            utc_time = (
                run.created_at.replace(tzinfo=ZoneInfo("UTC"))
                if run.created_at.tzinfo is None
                else run.created_at
            )
            created_at_str = utc_time.astimezone(local_tz).isoformat()

        result.append({
            "run_id": str(run.id),
            "job_id": run.job_id or "N/A",
            "job_name": job_name or connector_name,
            "connector": connector_name,
            "status": run.status,
            "processing_status": run.processing_status or "not_required",
            "selected_filename": run.selected_filename,
            "selected_sheet": run.selected_sheet,
            "processing_error": run.processing_error,
            "report_date": run.report_date,
            "history_date": run.history_date,
            "node": run.execution_node or "N/A",
            "created_at": created_at_str,
        })

    return result
