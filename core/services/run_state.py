import json
import logging
import os
from typing import Optional

import redis.asyncio as redis

from core.config import settings
from core.models.mongo_models import Run
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS = {
    "queued": {"running", "failed"},
    "running": {"success", "failed"},
    "success": set(),
    "failed": {"queued"},
}


def _get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=False)


class RunStateModule:
    @staticmethod
    async def publish_update(run_id: str, status: str, execution_node: Optional[str] = None) -> None:
        try:
            redis_client = _get_redis_client()
            message = {
                "run_id": str(run_id),
                "status": status,
                "node": execution_node or os.getenv("HOSTNAME", "worker"),
                "timestamp": get_now().isoformat(),
            }
            await redis_client.publish("run_updates", json.dumps(message))
        except Exception as exc:
            logger.error("Redis publish failed: %s", exc)

    @classmethod
    async def save_run_status(
        cls,
        run_id: str,
        status: str,
        *,
        error: Optional[str] = None,
        force: bool = False,
        publish: bool = True,
    ) -> bool:
        run = await Run.get(str(run_id))
        if not run:
            logger.error("[CRITICAL] Run %s not found in DB for status update.", run_id)
            return False

        current = str(run.status or "")
        if not force and current != status:
            allowed = ALLOWED_TRANSITIONS.get(current, set())
            if status not in allowed:
                logger.warning(
                    "Run %s transition blocked: %s -> %s (allowed=%s)",
                    run_id,
                    current,
                    status,
                    sorted(allowed),
                )
                return False

        execution_node = os.getenv("HOSTNAME", "worker")
        update_dict = {
            "status": status,
            "execution_node": execution_node,
            "updated_at": get_now(),
        }
        if error is not None:
            update_dict["error_summary"] = error
        if status == "running":
            update_dict["started_at"] = get_now()
            update_dict["finished_at"] = None
        elif status in {"success", "failed"}:
            update_dict["finished_at"] = get_now()

        await run.update({"$set": update_dict})
        if publish:
            await cls.publish_update(str(run_id), status, execution_node)
        return True

    @classmethod
    async def mark_failed_with_log(cls, run: Run, *, reason: str, log_message: str) -> None:
        timestamp = get_now()
        run.status = "failed"
        run.error_summary = reason
        run.finished_at = timestamp
        run.updated_at = timestamp
        run.logs.append(f"[{timestamp.time()}] {log_message}")
        await run.save()
        await cls.publish_update(str(run.id), "failed", run.execution_node)


run_state = RunStateModule()

