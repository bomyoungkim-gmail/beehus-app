"""
Celery tasks for the Beehus scraping platform.
Replaces the custom aio_pika worker implementation.
"""

from celery import Task
from django_config import celery_app
from core.worker.executor import SeleniumExecutor
from core.connectors.registry import ConnectorRegistry
from core.repositories import repo
from core.models.mongo_models import Job, Run, Credential
from core.db import init_db
from core.security import decrypt_value
import asyncio
import logging
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Base task that ensures Beanie is initialized"""
    _db_initialized = False
    
    def __call__(self, *args, **kwargs):
        # Initialize Beanie once per worker process
        if not self._db_initialized:
            asyncio.run(init_db())
            self.__class__._db_initialized = True
            logger.info("✅ Beanie initialized for Celery worker")
        
        return super().__call__(*args, **kwargs)


@celery_app.task(bind=True, max_retries=3, time_limit=1800)
def scrape_task(self, job_id: str, run_id: str, workspace_id: str, connector_name: str, params: dict):
    """
    Main scraping task - executes a connector with Selenium.
    """
    async def _async_scrape():
        await init_db()
        from core.models.mongo_models import Run
        from datetime import datetime
        
        try:
            # Get run document
            run = await Run.get(run_id)
            if not run:
                 logger.error(f"Run {run_id} not found")
                 return
            
            # Fetch job to check for credentials
            job = await Job.get(job_id)
            
            # Prepare execution params
            execution_params = params.copy()
            
            # Resolve and inject credentials if available
            if job and job.credential_id:
                credential = await Credential.get(job.credential_id)
                if credential:
                    execution_params["username"] = credential.username
                    decrypted_password = decrypt_value(credential.encrypted_password)
                    execution_params["password"] = decrypted_password
                    
                    # Inject extended metadata (agencia, conta, etc.)
                    if credential.metadata:
                        execution_params.update(credential.metadata)
                    if not decrypted_password:
                        logger.error(f"Credential decryption failed for job {job_id}")
                else:
                    logger.warning(f"Credential {job.credential_id} not found for job {job_id}")
            
            async def log(msg):
                logger.info(msg)
                if run:
                    # Atomic push to logs to avoid overwriting status
                    timestamped_msg = f"[{get_now().time()}] {msg}"
                    await run.update({"$push": {"logs": timestamped_msg}})

            # Heartbeat loop
            async def heartbeat_loop():
                while True:
                    try:
                        await asyncio.sleep(60)
                        if run:
                            # Atomic update of updated_at
                            await run.update({"$set": {"updated_at": get_now()}})
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Heartbeat error: {e}")

            # Update run status to running
            await repo.save_run_status(run_id, "running")
            await log(f"🔄 Starting scrape: run_id={run_id}, connector={connector_name}")
            
            # Start heartbeat
            heartbeat_task = asyncio.create_task(heartbeat_loop())

            # Get connector
            try:
                connector = ConnectorRegistry.get_connector(connector_name)
            except ValueError as e:
                msg = f"Connector '{connector_name}' not found"
                await log(f"❌ {msg}")
                await repo.save_run_status(run_id, "failed", msg)
                heartbeat_task.cancel()
                return {"success": False, "error": str(e)}
            
            # Execute scraping with Selenium
            # HYBRID ARCHITECTURE: 
            # - If JP Morgan: Use Local Undetected Chrome (Port 7901)
            # - Else, Use Remote Selenium Grid (Port 7900)
            use_local = "jpmorgan" in connector_name.lower()
            
            executor = SeleniumExecutor(use_local=use_local)
            executor.start()
            await log(f"🔌 Connected to Selenium Grid: {executor.driver.session_id}")
            
            try:
                # Add context to params
                params_with_context = {
                    **execution_params,
                    "run_id": run_id,
                    "job_id": job_id,
                    "workspace_id": workspace_id
                }
                
                # Execute connector
                await log("🚀 Executing connector logic...")
                result = await connector.scrape(executor.driver, params_with_context)
                
                # Save results
                if result.success:
                    await repo.save_run_status(run_id, "success")
                    if result.data:
                        await repo.save_raw_payload(
                            run_id, 
                            result.data.get('url', 'unknown'), 
                            str(result.data)
                        )
                    await log(f"✅ Scrape successful")
                else:
                    await repo.save_run_status(run_id, "failed", result.error)
                    await log(f"❌ Scrape failed: {result.error}")
                
                return result.dict() if hasattr(result, 'dict') else {"success": result.success, "data": result.data}
                
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                
                executor.stop()
                await log("🛑 Session ended")
                
        except Exception as e:
            logger.exception(f"❌ Scrape task exception: {e}")
            await repo.save_run_status(run_id, "failed", str(e))
            raise
    
    # Use existing event loop or create new one if needed
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(_async_scrape())


@celery_app.task(base=DatabaseTask, bind=True)
def cleanup_stale_runs(self):
    """
    Periodic task to cleanup stale/zombie runs.
    - Fails 'running' jobs with no heartbeat for > 5 mins
    - Fails 'queued' jobs older than > 1 hour
    """
    async def _cleanup():
        from datetime import datetime, timedelta
        
        # 1. Handle Zombie Running Jobs (No heartbeat)
        zombie_cutoff = get_now() - timedelta(minutes=5)
        zombies = await Run.find(
            Run.status == "running",
            Run.updated_at < zombie_cutoff
        ).to_list()
        
        for run in zombies:
            logger.warning(f"🧟 Found zombie run {run.id}. Marking failed.")
            run.status = "failed"
            run.error_summary = "Zombie execution detected (Heartbeat lost)"
            run.logs.append(f"[{get_now().time()}] 💀 System: Marked as zombie (no heartbeat > 5m)")
            run.finished_at = get_now()
            await run.save()
            
        # 2. Handle Stuck Queued Jobs
        queue_cutoff = get_now() - timedelta(hours=1)
        stuck_queued = await Run.find(
            Run.status == "queued",
            Run.created_at < queue_cutoff
        ).to_list()
        
        for run in stuck_queued:
            logger.warning(f"⏳ Found stuck queued run {run.id}. Marking failed.")
            run.status = "failed"
            run.error_summary = "Stuck in queue > 1h"
            run.logs.append(f"[{get_now().time()}] 💀 System: Timeout in queue")
            run.finished_at = get_now()
            await run.save()
            
        return f"Cleaned {len(zombies)} zombies and {len(stuck_queued)} stuck runs"
    
    return asyncio.run(_cleanup())


@celery_app.task(base=DatabaseTask, bind=True)
def cleanup_old_runs_task(self, days_old: int = 90):
    """
    Scheduled task to clean up old runs.
    
    Args:
        days_old: Delete runs older than this many days
    
    Returns:
        int: Number of runs deleted
    """
    async def _cleanup():
        from datetime import datetime, timedelta
        cutoff = get_now() - timedelta(days=days_old)
        
        # Delete old runs
        result = await Run.find(Run.created_at < cutoff).delete()
        deleted_count = result.deleted_count if hasattr(result, 'deleted_count') else 0
        
        logger.info(f"🗑️  Deleted {deleted_count} runs older than {days_old} days")
        return deleted_count
    
    return asyncio.run(_cleanup())


@celery_app.task(base=DatabaseTask, bind=True, max_retries=5, time_limit=300)
def otp_request_task(self, run_id: str, workspace_id: str, otp_rule_id: str = None):
    """
    Task to request OTP from inbox worker.
    This publishes to the otp.request queue for the inbox worker to handle.
    
    Args:
        run_id: Run ID that needs OTP
        workspace_id: Workspace ID
        otp_rule_id: Optional specific OTP rule to use
    
    Returns:
        dict: OTP request result
    """
    # TODO: Implement OTP request logic
    # This would publish to RabbitMQ otp.request queue
    # For now, just log
    logger.info(f"📧 OTP request: run_id={run_id}, workspace={workspace_id}")
    return {"status": "otp_requested", "run_id": run_id}


# ---------------------------------------------------
# Scheduled Job Runner
# ---------------------------------------------------
@celery_app.task(bind=True)
def scheduled_job_runner(self, job_id: str):
    """
    Task triggered by Celery Beat for scheduled jobs.
    Automatically creates a run and executes the job.
    """
    async def _run_scheduled():
        await init_db()
        from core.models.mongo_models import Job, Run
        
        # Get job details
        job = await Job.get(job_id)
        if not job or job.status != "active":
            logger.warning(f"Job {job_id} not found or inactive")
            return
        
        # Create run
        run = Run(job_id=job_id, connector=job.connector, status="queued", logs=["[System] Scheduled execution"])
        await run.save()
        
        logger.info(f"📅 Scheduled job triggered: {job_id}, run: {run.id}")
        
        # Dispatch to regular scrape task
        scrape_task.delay(
            job_id=job_id,
            run_id=str(run.id),
            workspace_id=job.workspace_id,
            connector_name=job.connector,
            params=job.params
        )
        
        return {"job_id": job_id, "run_id": str(run.id)}
    
    return asyncio.run(_run_scheduled())