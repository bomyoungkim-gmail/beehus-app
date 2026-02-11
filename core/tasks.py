"""
Celery tasks for the Beehus scraping platform.
Replaces the custom aio_pika worker implementation.
"""

from celery import Task
from django_config import celery_app
from core.worker.executor import SeleniumExecutor
from core.services.file_manager import FileManager
from core.connectors.registry import ConnectorRegistry
from datetime import datetime
import os
import shutil
from core.repositories import repo
from core.models.mongo_models import Job, Run, Credential
from core.db import init_db
from core.security import decrypt_value
from core.config import settings
import asyncio
import logging
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)

SELENIUM_SLOT_KEY = "selenium:slots"
SELENIUM_SLOT_INIT_KEY = "selenium:slots:initialized"
SELENIUM_MAX_SLOTS = max(
    1,
    settings.SELENIUM_MAX_SLOTS,
    settings.SELENIUM_NODE_COUNT * settings.SELENIUM_NODE_MAX_SESSIONS,
)


async def _ensure_selenium_slots(redis_client) -> None:
    """Ensure the Selenium slot pool exists in Redis."""
    # Use SETNX to avoid re-initializing the slot pool
    initialized = await redis_client.setnx(SELENIUM_SLOT_INIT_KEY, "1")
    if initialized:
        # Pre-fill the slot pool with N tokens
        tokens = [f"slot-{i}" for i in range(SELENIUM_MAX_SLOTS)]
        await redis_client.delete(SELENIUM_SLOT_KEY)
        if tokens:
            await redis_client.rpush(SELENIUM_SLOT_KEY, *tokens)


async def _acquire_selenium_slot(run_id: str, timeout_seconds: int = 300) -> str | None:
    """Acquire a Selenium slot token to limit concurrent sessions."""
    try:
        import redis.asyncio as redis
    except Exception as e:
        logger.error(f"Redis client not available for slot control: {e}")
        return None

    redis_client = redis.from_url(settings.REDIS_URL)
    try:
        await _ensure_selenium_slots(redis_client)
        start = get_now()
        while True:
            result = await redis_client.brpop(SELENIUM_SLOT_KEY, timeout=5)
            if result:
                _, token = result
                token_str = token.decode() if isinstance(token, (bytes, bytearray)) else str(token)
                logger.info(f"✅ Acquired Selenium slot {token_str} for run {run_id}")
                return token_str
            waited = (get_now() - start).total_seconds()
            if waited >= timeout_seconds:
                logger.error(f"⏳ Timed out waiting for Selenium slot after {timeout_seconds}s")
                return None
            logger.info("⏳ Waiting for Selenium slot...")
    finally:
        await redis_client.close()


async def _release_selenium_slot(token: str) -> None:
    """Release a Selenium slot token back to the pool."""
    if not token:
        return
    try:
        import redis.asyncio as redis
    except Exception as e:
        logger.error(f"Redis client not available for slot release: {e}")
        return

    redis_client = redis.from_url(settings.REDIS_URL)
    try:
        await redis_client.lpush(SELENIUM_SLOT_KEY, token)
        logger.info(f"🔓 Released Selenium slot {token}")
    finally:
        await redis_client.close()


class DatabaseTask(Task):
    """Base task that ensures Beanie is initialized"""
    _db_initialized = False
    
    def __call__(self, *args, **kwargs):
        """Initialize the database once per worker process before running the task."""
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
        """Async implementation of the scraping task."""
        await init_db()
        run_download_dir = None
        
        try:
            # Get run document
            run = await Run.get(run_id)
            if not run:
                 logger.error(f"Run {run_id} not found")
                 return
            
            # Fetch job to check for credentials
            job = await Job.get(job_id)
            download_root = os.getenv("DOWNLOADS_DIR", "/downloads")
            run_download_dir = os.path.join(download_root, run_id)
            os.makedirs(run_download_dir, exist_ok=True)
            if run and job and job.name:
                await run.update({"$set": {"job_name": job.name}})
            
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
                """Write a message to logs and the run document."""
                logger.info(msg)
                if run:
                    # Atomic push to logs to avoid overwriting status
                    timestamped_msg = f"[{get_now().time()}] {msg}"
                    await run.update({"$push": {"logs": timestamped_msg}})

            # Heartbeat loop
            async def heartbeat_loop():
                """Keep the run updated while the task is active."""
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
            
            slot_token = None
            if not use_local:
                slot_token = await _acquire_selenium_slot(run_id)
                if not slot_token:
                    msg = "No Selenium slot available within timeout"
                    await log(f"❌ {msg}")
                    await repo.save_run_status(run_id, "failed", msg)
                    heartbeat_task.cancel()
                    return {"success": False, "error": msg}

            executor = SeleniumExecutor(use_local=use_local, download_dir=run_download_dir)
            executor.start()
            await log(f"🔌 Connected to Selenium Grid: {executor.driver.session_id}")
            if run:
                if executor.vnc_url:
                    await run.update({"$set": {"vnc_url": executor.vnc_url}})
            
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
                    
                    # Capture and process downloaded files
                    await log("📁 Checking for downloaded files...")
                    try:
                        # Capture files from downloads
                        original_paths = FileManager.capture_downloads(
                            run_id,
                            pattern="*",
                            source_dir=run_download_dir,
                        )
                        
                        if original_paths:
                            # Extract metadata for processed naming
                            job = await Job.get(job_id)
                            metadata = {
                                'bank': connector_name.replace('conn_', '').replace('_', ' ').title(),
                                'account': params_with_context.get('conta', params_with_context.get('account', '0000')),
                                'date': datetime.now().strftime('%d%m%Y')
                            }
                            
                            files_metadata = []
                            for idx, original_path in enumerate(original_paths, start=1):
                                suffix = str(idx) if len(original_paths) > 1 else ""

                                # Rename original file to standardized output name
                                renamed_original = FileManager.rename_file(
                                    original_path,
                                    metadata,
                                    suffix=suffix
                                ) or original_path

                                # Process file to standardized output name
                                processed_path = FileManager.process_file(
                                    renamed_original,
                                    run_id,
                                    metadata,
                                    suffix=suffix
                                )
                                
                                files_metadata.append({
                                    'file_type': 'original',
                                    'filename': os.path.basename(renamed_original),
                                    'path': FileManager.to_artifact_relative(renamed_original),
                                    'size_bytes': FileManager.get_file_size(renamed_original),
                                    'status': 'ready'
                                })
                                
                                if processed_path:
                                    files_metadata.append({
                                        'file_type': 'processed',
                                        'filename': os.path.basename(processed_path),
                                        'path': FileManager.to_artifact_relative(processed_path),
                                        'size_bytes': FileManager.get_file_size(processed_path),
                                        'status': 'ready'
                                    })
                            
                            if files_metadata:
                                await run.update({"$set": {"files": files_metadata}})
                                await log(f"✅ Files captured: {len(files_metadata)} file(s)")
                        else:
                            await log("ℹ️  No files downloaded")
                    
                    except Exception as file_error:
                        await log(f"⚠️  File processing error: {file_error}")
                        # Don't fail the job if file processing fails
                    
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
                if slot_token:
                    await _release_selenium_slot(slot_token)
                await log("🛑 Session ended")
                
        except Exception as e:
            logger.exception(f"❌ Scrape task exception: {e}")
            await repo.save_run_status(run_id, "failed", str(e))
            raise
        finally:
            if run_download_dir and os.path.isdir(run_download_dir):
                try:
                    shutil.rmtree(run_download_dir, ignore_errors=True)
                    logger.info(f"🧹 Removed run download dir: {run_download_dir}")
                except Exception as cleanup_error:
                    logger.warning(f"Could not remove run download dir {run_download_dir}: {cleanup_error}")
    
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
        """Async implementation of stale run cleanup."""
        from datetime import timedelta
        
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
        """Async implementation of old run cleanup."""
        from datetime import timedelta
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
        """Async implementation of scheduled job runner."""
        await init_db()
        from core.models.mongo_models import Job, Run
        
        # Get job details
        job = await Job.get(job_id)
        if not job or job.status != "active":
            logger.warning(f"Job {job_id} not found or inactive")
            return
        
        # Create run
        run = Run(
            job_id=job_id,
            job_name=job.name,
            connector=job.connector,
            status="queued",
            logs=["[System] Scheduled execution"],
        )
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
