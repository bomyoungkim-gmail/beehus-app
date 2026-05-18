"""
Celery tasks for the Beehus scraping platform.
Replaces the custom aio_pika worker implementation.
"""

from celery import Task
from django_config import celery_app
from core.connectors.registry import ConnectorRegistry
from core.repositories import repo
from core.models.mongo_models import Job, Run, Credential, OtpAudit
from core.db import init_db
from core.security import decrypt_value
from core.config import settings
import os
import asyncio
import logging
import importlib
import unicodedata
import socket
import hashlib
import inspect
import pkgutil
from pathlib import Path
from datetime import datetime
import re
from core.utils.date_utils import get_now
from core.services.run_state import run_state
from core.services.run_execution import run_execution
import core.connectors
from core.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

SELENIUM_SLOT_KEY = "selenium:slots"
SELENIUM_SLOT_INIT_KEY = "selenium:slots:initialized"
SELENIUM_SLOT_ACTIVE_KEY = "selenium:slots:active"
SELENIUM_SLOT_MAX_AGE_SECONDS = 1800  # reclaim slots held longer than 30 min
SELENIUM_MAX_SLOTS = max(
    1,
    settings.SELENIUM_MAX_SLOTS,
    settings.SELENIUM_NODE_COUNT * settings.SELENIUM_NODE_MAX_SESSIONS,
)
_BUILD_FINGERPRINT_CACHE: str | None = None


def _resolve_connector_with_reload(connector_name: str):
    """
    Resolve connector and recover from stale/partial registry state in long-lived workers.
    """
    def _resolve_by_direct_module_scan(name: str):
        """
        Last-resort connector resolution bypassing registry static state.
        Scans conn_* modules, instantiates subclasses and matches by .name.
        """
        discovered_modules: list[str] = []
        for module_info in pkgutil.iter_modules(core.connectors.__path__):
            module_name = module_info.name
            if not module_name.startswith("conn_"):
                continue
            fq_module = f"core.connectors.{module_name}"
            discovered_modules.append(fq_module)
            try:
                module = importlib.import_module(fq_module)
            except Exception:
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, BaseConnector) or obj is BaseConnector:
                    continue
                if obj.__module__ != module.__name__:
                    continue
                try:
                    instance = obj()
                except Exception:
                    continue
                if getattr(instance, "name", None) == name:
                    try:
                        ConnectorRegistry.register(obj)
                    except Exception:
                        pass
                    return instance, discovered_modules
        return None, discovered_modules

    try:
        return ConnectorRegistry.get_connector(connector_name), False
    except ValueError:
        # Force re-import of registry module so connector registrations run again.
        registry_module = importlib.import_module("core.connectors.registry")
        reloaded_module = importlib.reload(registry_module)
        reloaded_registry = getattr(reloaded_module, "ConnectorRegistry", ConnectorRegistry)
        try:
            return reloaded_registry.get_connector(connector_name), True
        except ValueError:
            connector, discovered_modules = _resolve_by_direct_module_scan(connector_name)
            if connector:
                return connector, True
            raise ValueError(
                f"Connector '{connector_name}' not found after reload+scan. "
                f"Scanned modules: {discovered_modules}"
            )


def _diagnose_connector_lookup(connector_name: str) -> dict:
    """Best-effort diagnostics for connector lookup failures."""
    diagnostics: dict = {
        "connector_name": connector_name,
        "registry_keys": sorted(getattr(ConnectorRegistry, "_registry", {}).keys()),
        "module_candidates": [],
    }
    base = connector_name
    if base.endswith("_login"):
        base = base[: -len("_login")]
    candidates = [
        f"core.connectors.conn_{connector_name}",
        f"core.connectors.conn_{base}",
    ]

    seen = set()
    for module_name in candidates:
        if module_name in seen:
            continue
        seen.add(module_name)
        entry = {"module": module_name}
        try:
            module = importlib.import_module(module_name)
            entry["import"] = "ok"
            discovered = []
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, BaseConnector) or obj is BaseConnector:
                    continue
                if obj.__module__ != module.__name__:
                    continue
                item = {"class": obj.__name__}
                try:
                    instance = obj()
                    item["name"] = getattr(instance, "name", None)
                except Exception as class_exc:
                    item["init_error"] = f"{type(class_exc).__name__}: {class_exc}"
                discovered.append(item)
            entry["connector_classes"] = discovered
        except Exception as import_exc:
            entry["import"] = "error"
            entry["error"] = f"{type(import_exc).__name__}: {import_exc}"
        diagnostics["module_candidates"].append(entry)
    return diagnostics


def _normalize_connector_name(raw_name: str | None) -> str:
    """
    Normalize connector names received from persisted jobs/queue payloads.
    Handles hidden unicode formatting chars and surrounding spaces.
    """
    if raw_name is None:
        return ""
    name = str(raw_name)
    name = "".join(ch for ch in name if unicodedata.category(ch) != "Cf")
    return name.strip()


def _hash_files(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for file_path in paths:
        try:
            data = Path(file_path).read_bytes()
        except Exception:
            continue
        digest.update(file_path.encode("utf-8", errors="ignore"))
        digest.update(data)
    return digest.hexdigest()[:12]


def _build_fingerprint() -> str:
    """
    Build fingerprint to identify exactly which runtime processed the run.
    Priority:
      1) explicit BUILD_FINGERPRINT / GIT_SHA envs
      2) fallback deterministic hash from core worker files
    """
    global _BUILD_FINGERPRINT_CACHE
    if _BUILD_FINGERPRINT_CACHE:
        return _BUILD_FINGERPRINT_CACHE

    explicit_fp = (
        os.getenv("BUILD_FINGERPRINT")
        or os.getenv("GIT_SHA")
        or os.getenv("GIT_COMMIT")
        or os.getenv("COMMIT_SHA")
    )
    if explicit_fp:
        source = "env"
        fp = explicit_fp.strip()
    else:
        source = "hash"
        fp = _hash_files(
            [
                "/app/core/tasks.py",
                "/app/core/connectors/registry.py",
                "/app/core/connectors/conn_morgan_stanley.py",
            ]
        )

    host = os.getenv("HOSTNAME") or socket.gethostname()
    image_tag = os.getenv("IMAGE_TAG") or os.getenv("APP_IMAGE_TAG") or "-"
    compose_project = os.getenv("COMPOSE_PROJECT_NAME") or "-"
    _BUILD_FINGERPRINT_CACHE = (
        f"source={source} fp={fp} host={host} image={image_tag} compose={compose_project}"
    )
    return _BUILD_FINGERPRINT_CACHE


def _resolve_credential_password(credential: Credential, execution_params: dict) -> tuple[str | None, str]:
    """
    Resolve the best password source for a credential.

    Order:
    1) Decrypted credential password (expected path)
    2) Legacy plaintext accidentally saved in encrypted_password
    3) Explicit job params password/pass
    4) Credential metadata password/pass
    """
    decrypted_password = decrypt_value(credential.encrypted_password)
    if decrypted_password:
        return decrypted_password, "credential_decrypted"

    raw_encrypted = str(credential.encrypted_password or "").strip()
    if raw_encrypted and not raw_encrypted.startswith("gAAAAA"):
        return raw_encrypted, "credential_legacy_plaintext"

    params_password = (execution_params.get("password") or execution_params.get("pass") or "").strip()
    if params_password:
        return params_password, "job_params"

    metadata = credential.metadata if isinstance(credential.metadata, dict) else {}
    metadata_password = (metadata.get("password") or metadata.get("pass") or "").strip()
    if metadata_password:
        return metadata_password, "credential_metadata"

    return None, "missing"


def _to_ddmmyyyy(value: str | None, *, prefer_month_first: bool = False) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").strftime("%d%m%Y")
        except ValueError:
            return None

    # 19/02/2026, 04/02/2026, 19-02-2026 (supports both day/month and month/day)
    m = re.match(r"^(\d{2})[/-](\d{2})[/-](\d{4})$", s)
    if m:
        first, second, year = m.group(1), m.group(2), m.group(3)
        token = f"{first}/{second}/{year}"
        ordered_formats = ["%m/%d/%Y", "%d/%m/%Y"] if prefer_month_first else ["%d/%m/%Y", "%m/%d/%Y"]
        for fmt in ordered_formats:
            try:
                return datetime.strptime(token, fmt).strftime("%d%m%Y")
            except ValueError:
                continue

    # 19022026 / 04022026 / 20260219
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        ordered_formats = ["%m%d%Y", "%d%m%Y", "%Y%m%d"] if prefer_month_first else ["%d%m%Y", "%m%d%Y", "%Y%m%d"]
        for fmt in ordered_formats:
            try:
                return datetime.strptime(digits, fmt).strftime("%d%m%Y")
            except ValueError:
                continue
    return None


def _is_history_file(filename: str) -> bool:
    name = (filename or "").lower()
    history_markers = [
        "extrato",
        "historico",
        "historico",
        "history",
        "transaction",
        "moviment",
    ]
    return any(marker in name for marker in history_markers)


async def _ensure_selenium_slots(redis_client) -> None:
    """Ensure the Selenium slot pool exists in Redis."""
    initialized = await redis_client.setnx(SELENIUM_SLOT_INIT_KEY, "1")
    if initialized:
        tokens = [f"slot-{i}" for i in range(SELENIUM_MAX_SLOTS)]
        await redis_client.delete(SELENIUM_SLOT_KEY)
        if tokens:
            await redis_client.rpush(SELENIUM_SLOT_KEY, *tokens)
        return

    # Pool was previously initialized — check if fully drained with no active holders
    pool_size = await redis_client.llen(SELENIUM_SLOT_KEY)
    if pool_size == 0:
        active_count = await redis_client.hlen(SELENIUM_SLOT_ACTIVE_KEY)
        if active_count == 0:
            tokens = [f"slot-{i}" for i in range(SELENIUM_MAX_SLOTS)]
            await redis_client.rpush(SELENIUM_SLOT_KEY, *tokens)
            logger.warning(f"♻️ Pool vazio sem holders ativos — reinicializados {SELENIUM_MAX_SLOTS} slots")


async def _reclaim_stale_slots(redis_client) -> int:
    """Return any slots held beyond SELENIUM_SLOT_MAX_AGE_SECONDS back to the pool."""
    import time

    active = await redis_client.hgetall(SELENIUM_SLOT_ACTIVE_KEY)
    reclaimed = 0
    now = time.time()
    for raw_token, raw_value in active.items():
        token = raw_token.decode() if isinstance(raw_token, bytes) else str(raw_token)
        value = raw_value.decode() if isinstance(raw_value, bytes) else str(raw_value)
        try:
            acquired_at = float(value.split(":", 1)[1])
        except (IndexError, ValueError):
            continue
        age = now - acquired_at
        if age > SELENIUM_SLOT_MAX_AGE_SECONDS:
            await redis_client.hdel(SELENIUM_SLOT_ACTIVE_KEY, token)
            await redis_client.lpush(SELENIUM_SLOT_KEY, token)
            logger.warning(f"♻️ Reclaimed stale Selenium slot {token} (held {age:.0f}s)")
            reclaimed += 1
    return reclaimed


async def _acquire_selenium_slot(run_id: str, timeout_seconds: int = 300) -> str | None:
    """Acquire a Selenium slot token to limit concurrent sessions."""
    import time

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
                await redis_client.hset(SELENIUM_SLOT_ACTIVE_KEY, token_str, f"{run_id}:{time.time()}")
                logger.info(f"✅ Acquired Selenium slot {token_str} for run {run_id}")
                return token_str
            waited = (get_now() - start).total_seconds()
            if waited >= timeout_seconds:
                reclaimed = await _reclaim_stale_slots(redis_client)
                if reclaimed:
                    logger.info(f"♻️ Reclaimed {reclaimed} stale slot(s), retrying acquisition for run {run_id}")
                    result = await redis_client.brpop(SELENIUM_SLOT_KEY, timeout=5)
                    if result:
                        _, token = result
                        token_str = token.decode() if isinstance(token, (bytes, bytearray)) else str(token)
                        await redis_client.hset(SELENIUM_SLOT_ACTIVE_KEY, token_str, f"{run_id}:{time.time()}")
                        logger.info(f"✅ Acquired Selenium slot {token_str} for run {run_id} after reclaim")
                        return token_str
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
        await redis_client.hdel(SELENIUM_SLOT_ACTIVE_KEY, token)
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


@celery_app.task(base=DatabaseTask, bind=True, max_retries=3, time_limit=1800)
def scrape_task(self, job_id: str, run_id: str, workspace_id: str, connector_name: str, params: dict):
    """
    Main scraping task - executes a connector with Selenium.
    """
    async def _async_scrape():
        """Async implementation of the scraping task."""
        nonlocal connector_name
        await init_db()
        job = None
        run_download_dir = None
        raw_connector_name = connector_name
        connector_name = _normalize_connector_name(connector_name)

        try:
            # Get run document
            run = await Run.get(run_id)
            if not run:
                 logger.error(f"Run {run_id} not found")
                 return
            
            async def log(msg):
                """Write a message to logs and the run document."""
                logger.info(msg)
                if run:
                    # Atomic push to logs to avoid overwriting status
                    timestamped_msg = f"[{get_now().time()}] {msg}"
                    await run.update({"$push": {"logs": timestamped_msg}})
            
            # Fetch job to check for credentials
            job = await Job.get(job_id)

            if run and job and job.name:
                await run.update({"$set": {"job_name": job.name}})
            
            # Prepare execution params
            execution_params = params.copy()

            # Resolve and inject credentials if available.
            # Fallback path supports legacy jobs saved without credential_id.
            credential = None
            credential_from_link = False

            if not job:
                await log(f"⚠️ Job {job_id} not found; running with provided params only")
            else:
                linked_credential_id = (job.credential_id or "").strip()
                if linked_credential_id:
                    credential = await Credential.get(linked_credential_id)
                    credential_from_link = True
                    if not credential:
                        await log(
                            f"⚠️ Credential {linked_credential_id} not found for job {job_id};"
                            " trying legacy fallback by username"
                        )

                # Legacy fallback for old jobs with empty credential_id.
                if not credential:
                    username_hint = (
                        execution_params.get("username")
                        or execution_params.get("user")
                        or ""
                    ).strip()
                    if username_hint:
                        credential = await Credential.find_one(
                            Credential.workspace_id == job.workspace_id,
                            Credential.username == username_hint,
                        )
                        if credential:
                            await job.update({"$set": {"credential_id": credential.id}})
                            job.credential_id = credential.id
                            await log(
                                "🔗 Auto-linked job credential by username/workspace match:"
                                f" credential_id={credential.id}"
                            )

            if credential:
                if credential_from_link:
                    # Explicitly linked credentials are source of truth.
                    execution_params["username"] = credential.username
                    resolved_password, password_source = _resolve_credential_password(
                        credential,
                        execution_params,
                    )
                    if resolved_password:
                        execution_params["password"] = resolved_password
                        if password_source != "credential_decrypted":
                            await log(
                                "⚠️ Credential password decryption failed;"
                                f" using fallback source={password_source} for credential {credential.id}"
                            )
                    else:
                        await log(
                            "❌ Credential password unavailable after decryption/fallbacks"
                            f" for credential {credential.id}. Check DATABASE_ENCRYPTION_KEY"
                            " and credential password data."
                        )
                else:
                    # Fallback mode: keep manual values if present, fill only gaps.
                    execution_params.setdefault("username", credential.username)
                    if not (execution_params.get("password") or execution_params.get("pass")):
                        resolved_password, _ = _resolve_credential_password(
                            credential,
                            execution_params,
                        )
                        if resolved_password:
                            execution_params["password"] = resolved_password

                metadata = credential.metadata if isinstance(credential.metadata, dict) else {}
                if metadata:
                    execution_params.update(metadata)
                    await log(
                        f"🔑 Injected credential metadata keys: {sorted(metadata.keys())}"
                    )
            else:
                await log("ℹ️ No credential metadata injected for this run")

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
            await run_state.save_run_status(run_id, "running")
            await log(f"🧬 Build fingerprint: {_build_fingerprint()}")
            if raw_connector_name != connector_name:
                await log(
                    "⚠️ Normalized connector name from "
                    f"{raw_connector_name!r} to {connector_name!r}"
                )
            await log(f"🔄 Starting scrape: run_id={run_id}, connector={connector_name}")
            
            # Start heartbeat
            heartbeat_task = asyncio.create_task(heartbeat_loop())

            # Get connector
            try:
                connector, recovered_with_reload = _resolve_connector_with_reload(connector_name)
                if recovered_with_reload:
                    await log(
                        f"⚠️ Connector registry reloaded during lookup and recovered connector '{connector_name}'"
                    )
            except ValueError as e:
                msg = f"Connector '{connector_name}' not found"
                diagnostics = _diagnose_connector_lookup(connector_name)
                await log(f"DEBUG Connector lookup exception: {e}")
                await log(
                    "DEBUG Available connectors in worker: "
                    f"{diagnostics.get('registry_keys', [])}"
                )
                await log(
                    "DEBUG Connector module diagnostics: "
                    f"{diagnostics.get('module_candidates', [])}"
                )
                await log(f"❌ {msg}")
                await run_state.save_run_status(run_id, "failed", error=msg)
                heartbeat_task.cancel()
                return {"success": False, "error": str(e)}
            
            # Execute scraping with Selenium
            # HYBRID ARCHITECTURE:
            # - JP Morgan: local worker NoVNC endpoint (UC/evasion)
            # - Morgan Stanley: optional local UC/evasion via env flag
            # - Others: remote Selenium Grid nodes (host ports 17902/17903 by default)
            execution_plan = run_execution.build_plan(connector_name)
            await log(
                "DEBUG Selenium execution mode: "
                f"{execution_plan.mode_label} "
                f"(connector={connector_name})"
            )
            
            slot_token = None
            if not execution_plan.use_local:
                slot_token = await _acquire_selenium_slot(run_id)
                if not slot_token:
                    msg = "No Selenium slot available within timeout"
                    await log(f"❌ {msg}")
                    await run_state.save_run_status(run_id, "failed", error=msg)
                    heartbeat_task.cancel()
                    return {"success": False, "error": msg}

            try:
                download_context = run_execution.prepare_download_context(run_id)
                run_download_dir = download_context.run_download_dir
            except Exception as snapshot_error:
                logger.warning("Failed to snapshot preexisting downloads: %s", snapshot_error)
                download_context = run_execution.prepare_download_context(run_id)
                run_download_dir = download_context.run_download_dir
            await log(f"Session download dir: {run_download_dir}")

            # Strong isolation: each run gets its own browser download directory.
            chrome_download_dir = run_download_dir
            
            executor = run_execution.start_executor(execution_plan, chrome_download_dir)
            await log(f"🔌 Connected to Selenium Grid: {executor.driver.session_id}")
            await log(
                "📺 VNC mapping:"
                f" node_id={executor.node_id or '-'}"
                f" node_uri={executor.node_uri or '-'}"
                f" vnc_url={executor.vnc_url or '-'}"
            )
            if run:
                if executor.vnc_url:
                    await run.update({"$set": {"vnc_url": executor.vnc_url}})
            
            result_payload = None
            no_files_downloaded = False
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
                    await run_state.save_run_status(run_id, "success")
                    if result.data:
                        await repo.save_raw_payload(
                            run_id,
                            result.data.get('url', 'unknown'),
                            str(result.data)
                        )

                    await log("✅ Scrape successful")
                else:
                    await run_state.save_run_status(run_id, "failed", error=result.error)
                    await log(f"❌ Scrape failed: {result.error}")

                await log("Checking for downloaded files...")
                try:
                    files_captured = await run_execution.capture_download_artifacts(
                        run_id=run_id,
                        run=run,
                        connector_name=connector_name,
                        execution_params=execution_params,
                        context=download_context,
                        to_ddmmyyyy=lambda value, prefer_month_first: _to_ddmmyyyy(
                            value,
                            prefer_month_first=prefer_month_first,
                        ),
                        is_history_file=_is_history_file,
                        log=log,
                    )
                    no_files_downloaded = not files_captured

                except Exception as file_error:
                    await log(f"File capture error: {file_error}")

                result_payload = (
                    result.model_dump()
                    if hasattr(result, "model_dump")
                    else getattr(result, "dict")()
                    if hasattr(result, "dict")
                    else {"success": result.success, "data": result.data}
                )
                # Guard against false-positive "success" when connector flow finishes
                # but no downloadable artifact is produced.
                connectors_requiring_downloads = {
                    "jefferies_login",
                    "jpmorgan_login",
                    "itau_onshore_login",
                    "btg_us_login",
                    "btg_cayman_login",
                }
                if (
                    result.success
                    and no_files_downloaded
                    and connector_name in connectors_requiring_downloads
                ):
                    no_file_msg = (
                        "Connector flow ended without downloaded files; "
                        "treating run as failed to avoid false success."
                    )
                    await run_state.save_run_status(run_id, "failed", error=no_file_msg)
                    await log(f"❌ {no_file_msg}")
                    if isinstance(result_payload, dict):
                        result_payload["success"] = False
                        result_payload["error"] = no_file_msg

            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                
                await run_execution.close_execution(
                    executor=executor,
                    slot_token=slot_token,
                    run_download_dir=run_download_dir,
                    release_slot=_release_selenium_slot,
                    log=log,
                )

            # -------------------------------------------------------------------------
            # Post-Processing (Selenium Released)
            # -------------------------------------------------------------------------
            if result_payload is not None and job:
                resolved_script = None
                if job.enable_processing:
                    from core.services.file_processor import FileProcessorService
                    resolved_script, _ = FileProcessorService.resolve_job_processing_script(job)
                should_process = bool(job.enable_processing and (resolved_script or "").strip())
                if job.enable_processing and not should_process:
                    await log("ℹ️ Processing enabled on job, but no script configured yet")

                if should_process:
                    from core.services.file_processor import FileProcessorService

                    await log("🔄 Processing files (Selenium released)...")
                    try:
                        processing_state = await FileProcessorService.resolve_and_process_post_scrape(
                            run_id=run_id,
                            job_id=job.id,
                            credential_id=job.credential_id,
                        )
                        if processing_state == "processed":
                            await log("✅ Processed files generated successfully")
                        elif processing_state in {"pending_file_selection", "pending_sheet_selection"}:
                            await log(f"⏸️ Waiting for user action: {processing_state}")
                        elif processing_state == "not_required":
                            await log("ℹ️ No original files available for processing")
                        else:
                            await log(f"⚠️ File processing ended with state: {processing_state}")
                    except Exception as proc_error:
                        await log(f"⚠️ File processing error: {proc_error}")
                        # Do not fail the run if processing fails, as scraping was successful
                else:
                    await log("ℹ️ File processing disabled for this job")

            return result_payload
                
        except Exception as e:
            logger.exception(f"❌ Scrape task exception: {e}")
            await run_state.save_run_status(run_id, "failed", error=str(e), force=True)
            raise
    
    return asyncio.run(_async_scrape())


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
            await run_state.mark_failed_with_log(
                run,
                reason="Zombie execution detected (Heartbeat lost)",
                log_message="💀 System: Marked as zombie (no heartbeat > 5m)",
            )
            
        # 2. Handle Stuck Queued Jobs
        queue_cutoff = get_now() - timedelta(hours=1)
        stuck_queued = await Run.find(
            Run.status == "queued",
            Run.created_at < queue_cutoff
        ).to_list()
        
        for run in stuck_queued:
            logger.warning(f"⏳ Found stuck queued run {run.id}. Marking failed.")
            await run_state.mark_failed_with_log(
                run,
                reason="Stuck in queue > 1h",
                log_message="💀 System: Timeout in queue",
            )
            
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
    async def _request_otp():
        """Persist OTP request audit and publish request to Redis-backed channel/list."""
        await init_db()

        request_payload = {
            "run_id": str(run_id),
            "workspace_id": str(workspace_id),
            "otp_rule_id": str(otp_rule_id) if otp_rule_id else None,
            "requested_at": get_now().isoformat(),
        }

        # Persist audit trail for observability/debugging
        audit = OtpAudit(
            run_id=str(run_id),
            workspace_id=str(workspace_id),
            otp_rule_id=str(otp_rule_id) if otp_rule_id else None,
            status="requested",
            detail="OTP request queued for inbox worker",
        )
        await audit.save()

        # Publish request for async inbox worker consumption
        redis_client = None
        try:
            import redis.asyncio as redis

            redis_client = redis.from_url(settings.REDIS_URL)
            payload_json = json.dumps(request_payload)
            await redis_client.lpush("otp:requests", payload_json)
            await redis_client.publish("otp.request", payload_json)
        finally:
            if redis_client is not None:
                await redis_client.close()

        logger.info(
            "📧 OTP request queued: run_id=%s workspace_id=%s otp_rule_id=%s",
            run_id,
            workspace_id,
            otp_rule_id,
        )
        return {
            "status": "otp_requested",
            "run_id": str(run_id),
            "workspace_id": str(workspace_id),
            "otp_rule_id": str(otp_rule_id) if otp_rule_id else None,
        }

    return asyncio.run(_request_otp())


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

        execution_params = (job.params or {}).copy()
        execution_params.update(
            {
                "export_holdings": job.export_holdings,
                "export_history": job.export_history,
                "date_mode": job.date_mode,
                "holdings_lag_days": job.holdings_lag_days,
                "history_lag_days": job.history_lag_days,
                "holdings_date": job.holdings_date,
                "history_date": job.history_date,
            }
        )
        
        # Dispatch to regular scrape task
        scrape_task.delay(
            job_id=job_id,
            run_id=str(run.id),
            workspace_id=job.workspace_id,
            connector_name=job.connector,
            params=execution_params
        )
        
        return {"job_id": job_id, "run_id": str(run.id)}
    
    return asyncio.run(_run_scheduled())
