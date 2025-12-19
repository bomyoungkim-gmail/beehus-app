"""
Celery tasks for the Beehus scraping platform.
Replaces the custom aio_pika worker implementation.
"""

from celery import Task
from django_config import celery_app
from core.worker.executor import SeleniumExecutor
from core.connectors.registry import ConnectorRegistry
from core.repositories import repo
from core.models.mongo_models import Job, Run
from core.db import init_db
import asyncio
import logging

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
            
            async def log(msg):
                logger.info(msg)
                if run:
                    run.logs.append(f"[{datetime.now().time()}] {msg}")
                    await run.save()

            # Update run status to running
            await repo.save_run_status(run_id, "running")
            await log(f"🔄 Starting scrape: run_id={run_id}, connector={connector_name}")
            
            # Get connector
            try:
                connector = ConnectorRegistry.get_connector(connector_name)
            except ValueError as e:
                msg = f"Connector '{connector_name}' not found"
                await log(f"❌ {msg}")
                await repo.save_run_status(run_id, "failed", msg)
                return {"success": False, "error": str(e)}
            
            # Execute scraping with Selenium
            executor = SeleniumExecutor()
            executor.start()
            await log(f"🔌 Connected to Selenium Grid: {executor.driver.session_id}")
            
            try:
                # Add context to params
                params_with_context = {
                    **params,
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
                executor.stop()
                await log("🛑 Session ended")
                
        except Exception as e:
            logger.exception(f"❌ Scrape task exception: {e}")
            await repo.save_run_status(run_id, "failed", str(e))
            raise
    
    return asyncio.run(_async_scrape())


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
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        
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
        run = Run(job_id=job_id, status="queued", logs=["[System] Scheduled execution"])
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


# ---------------------------------------------------
# scrap JPMorgan com Selenium Remoto
# ---------------------------------------------------
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime



@celery_app.task(bind=True, max_retries=3, time_limit=1800)
def login_to_jpmorgan_task(self, user, password, run_id=None):
    """
    Task assíncrona para login no JPMorgan seguindo o padrão Beehus.
    Adaptação para usar SeleniumExecutor e Run model.
    """
    
    async def _async_login():
        await init_db()
        _url = "https://secure.chase.com/web/auth/?treatment=jpo#/logon/logon/chaseOnline"
        
        # Ensure run exists or create a temp one if not provided (for testing)
        if run_id:
            run = await Run.get(run_id)
        else:
            run = None # Standalone execution test

        async def log(msg):
            logger.info(msg)
            if run:
                run.logs.append(f"[{datetime.now().time()}] {msg}")
                await run.save()

        await log(f"🔄 Iniciando login JPMorgan: user={user}")

        executor = SeleniumExecutor()
        executor.start()
        driver = executor.driver
        
        # Save node information to run
        if run and executor.node_id:
            run.node = executor.node_id
            await run.save()

        try:
            # 1. Navegação
            await log(f"NAVIGATE: {_url}")
            driver.get(_url)
            
            # 2. Preenchimento de campos
            await log("Waiting for user input field...")
            user_id_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "userId-input-field-input"))
            )
            user_id_field.send_keys(user)
            await log("Typed username")
            
            password_field = driver.find_element(By.ID, "password-input-field-input")
            password_field.send_keys(password)
            await log("Typed password")
            
            # Aguarda o tempo solicitado
            await asyncio.sleep(120)

            if run and run_id:
                await repo.save_run_status(run_id, "success")
            
            await log(f"✅ Login JPMorgan realizado com sucesso: {user}")
            return {"success": True, "user": user}

        except Exception as e:
            await log(f"❌ Erro durante o login JPMorgan: {str(e)}")
            if run and run_id:
                await repo.save_run_status(run_id, "failed", str(e))
            raise e
        finally:
            executor.stop()

    return asyncio.run(_async_login())