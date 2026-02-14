"""
File processing service for transforming downloaded files.
Executes Python scripts associated with credentials.
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from core.models.mongo_models import Credential, FileProcessor

logger = logging.getLogger(__name__)


class FileProcessorService:
    """Service for executing credential-bound file processors."""

    @staticmethod
    async def process_files(run_id: str, credential_id: str) -> List[str]:
        """
        Process files for a run using the credential's active processor.

        Args:
            run_id: Run ID
            credential_id: Credential ID

        Returns:
            List of processed file paths
        """
        try:
            processor = await FileProcessor.find_one(
                FileProcessor.credential_id == credential_id,
                FileProcessor.is_active == True,
            )
            if not processor:
                logger.info("No active processor for credential %s", credential_id)
                return []

            credential = await Credential.get(credential_id)
            if not credential:
                logger.warning("Credential %s not found", credential_id)
                return []

            artifacts_root = os.getenv("ARTIFACTS_DIR", "/app/artifacts")
            original_dir = Path(artifacts_root) / run_id / "original"
            processed_dir = Path(artifacts_root) / run_id / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)

            context = {
                "original_dir": str(original_dir),
                "processed_dir": str(processed_dir),
                "carteira": credential.carteira or "",
                "metadata": credential.metadata or {},
                "run_id": run_id,
                "credential_label": credential.label,
            }

            logger.info(
                "Executing processor '%s' (v%s) for run %s",
                processor.name,
                processor.version,
                run_id,
            )

            processed_files = await FileProcessorService._execute_processor(
                processor.script_content,
                context,
            )

            logger.info("Processor completed: %s file(s) generated", len(processed_files))
            return processed_files

        except Exception as exc:
            logger.error("File processing failed for run %s: %s", run_id, exc)
            return []

    @staticmethod
    async def _execute_processor(script: str, context: Dict) -> List[str]:
        """
        Execute a Python processor script in an isolated process.

        Args:
            script: Python code to execute
            context: Context variables available to the script

        Returns:
            List of processed file paths
        """
        script_path = None
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as handle:
            handle.write("# Auto-generated context\n")
            handle.write(f"original_dir = {context['original_dir']!r}\n")
            handle.write(f"processed_dir = {context['processed_dir']!r}\n")
            handle.write(f"carteira = {context.get('carteira', '')!r}\n")
            handle.write(f"metadata = {context.get('metadata', {})!r}\n")
            handle.write(f"run_id = {context['run_id']!r}\n")
            handle.write(f"credential_label = {context.get('credential_label', '')!r}\n\n")
            handle.write("# User script\n")
            handle.write(script)
            script_path = handle.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                timeout=300,
                capture_output=True,
                text=True,
                cwd=context["processed_dir"],
            )

            if result.returncode != 0:
                logger.error("Processor script failed: %s", result.stderr)
                raise RuntimeError(f"Processor failed: {result.stderr}")

            if result.stdout:
                logger.info("Processor output:\n%s", result.stdout)

            processed_dir = Path(context["processed_dir"])
            return [str(path) for path in processed_dir.glob("*") if path.is_file()]

        except subprocess.TimeoutExpired as exc:
            logger.error("Processor timeout (5 minutes)")
            raise RuntimeError("Processor timeout") from exc
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
