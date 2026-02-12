"""
File management service for downloaded and processed files.
Handles capture, renaming, and processing of files from Selenium downloads.
"""

import glob
import hashlib
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Base paths (can be overridden by environment variables)
DEFAULT_DOWNLOADS_DIR = "/downloads"  # Shared volume with Selenium nodes
DEFAULT_ARTIFACTS_DIR = "/app/artifacts"  # Persistent storage


class FileManager:
    """Manages file operations for downloaded and processed files."""

    @staticmethod
    def _downloads_dir() -> Path:
        return Path(os.getenv("DOWNLOADS_DIR", DEFAULT_DOWNLOADS_DIR))

    @staticmethod
    def _artifacts_dir() -> Path:
        return Path(os.getenv("ARTIFACTS_DIR", DEFAULT_ARTIFACTS_DIR))

    @staticmethod
    def _safe_component(value: str, fallback: str) -> str:
        """Normalize filename component to avoid invalid path chars."""
        clean = re.sub(r"[^A-Za-z0-9._-]", "", (value or "").replace(" ", ""))
        return clean or fallback

    @staticmethod
    def _file_signature(file_path: str, hash_bytes: int = 65536) -> Optional[tuple[int, int, str]]:
        """
        Build a lightweight signature for change detection.
        Returns (size_bytes, mtime_ns, sha1_prefix) or None if unavailable.
        """
        try:
            stat = os.stat(file_path)
            size = int(stat.st_size)
            mtime_ns = int(stat.st_mtime_ns)
            sha1 = hashlib.sha1()
            with open(file_path, "rb") as fh:
                sha1.update(fh.read(hash_bytes))
            return (size, mtime_ns, sha1.hexdigest())
        except Exception:
            return None

    @staticmethod
    def build_file_signatures(
        absolute_paths: set[str],
        hash_bytes: int = 65536,
    ) -> dict[str, tuple[int, int, str]]:
        """Build signatures map for a set of absolute file paths."""
        signatures: dict[str, tuple[int, int, str]] = {}
        for path in absolute_paths:
            sig = FileManager._file_signature(path, hash_bytes=hash_bytes)
            if sig:
                signatures[os.path.abspath(path)] = sig
        return signatures

    @staticmethod
    def to_artifact_relative(file_path: str) -> str:
        """
        Convert an absolute file path under artifacts root to relative POSIX path.
        """
        path = Path(file_path)
        artifacts_dir = FileManager._artifacts_dir().resolve()
        resolved = path.resolve()
        try:
            return resolved.relative_to(artifacts_dir).as_posix()
        except ValueError:
            # Fallback keeps behavior predictable if path is outside artifacts.
            return path.name

    @staticmethod
    def capture_download(
        run_id: str,
        pattern: str = "*.xlsx",
        timeout_seconds: int = 30,
        source_dir: Optional[str] = None,
        exclude_paths: Optional[set[str]] = None,
        min_modified_time: Optional[float] = None,
        preexisting_signatures: Optional[dict[str, tuple[int, int, str]]] = None,
    ) -> Optional[str]:
        """
        Capture a downloaded file from the downloads directory.

        Args:
            run_id: Run ID for organizing files
            pattern: Glob pattern to match downloaded files
            timeout_seconds: How long to wait for file to appear

        Returns:
            Path to captured file in artifacts directory, or None if not found
        """
        import time

        start_time = time.time()
        found_file = None
        downloads_dir = Path(source_dir) if source_dir else FileManager._downloads_dir()
        default_downloads_dir = FileManager._downloads_dir()

        def _list_complete_files(base_dir: Path) -> List[str]:
            files = glob.glob(str(base_dir / pattern))
            excluded = exclude_paths or set()
            return [
                f for f in files
                if (
                    os.path.isfile(f)
                    and not f.endswith((".crdownload", ".tmp", ".part"))
                    and (
                        os.path.abspath(f) not in excluded
                        or (
                            min_modified_time is not None
                            and os.path.getmtime(f) >= min_modified_time
                        )
                        or (
                            preexisting_signatures is not None
                            and (
                                FileManager._file_signature(f)
                                != preexisting_signatures.get(os.path.abspath(f))
                            )
                        )
                    )
                    and (
                        min_modified_time is None
                        or os.path.getmtime(f) >= min_modified_time
                    )
                )
            ]

        while time.time() - start_time < timeout_seconds:
            complete_files = _list_complete_files(downloads_dir)

            # Fallback for remote Selenium nodes that ignore run-specific folder.
            if (
                not complete_files
                and source_dir
                and downloads_dir.resolve() != default_downloads_dir.resolve()
            ):
                complete_files = _list_complete_files(default_downloads_dir)

            if complete_files:
                found_file = max(complete_files, key=os.path.getmtime)
                break

            time.sleep(1)

        if not found_file:
            logger.warning(f"No file matching '{pattern}' found in {downloads_dir} after {timeout_seconds}s")
            return None

        run_dir = FileManager._artifacts_dir() / run_id / "original"
        run_dir.mkdir(parents=True, exist_ok=True)

        filename = os.path.basename(found_file)
        dest_path = run_dir / filename

        try:
            shutil.move(found_file, dest_path)
            logger.info(f"Captured file: {filename} -> {dest_path}")
            return str(dest_path)
        except Exception as e:
            logger.error(f"Failed to move file {found_file}: {e}")
            return None

    @staticmethod
    def capture_downloads(
        run_id: str,
        pattern: str = "*.xlsx",
        timeout_seconds: int = 30,
        source_dir: Optional[str] = None,
        exclude_paths: Optional[set[str]] = None,
        min_modified_time: Optional[float] = None,
        preexisting_signatures: Optional[dict[str, tuple[int, int, str]]] = None,
    ) -> List[str]:
        """
        Capture all downloaded files from the downloads directory.

        Returns:
            List of captured file paths in artifacts directory.
        """
        import time

        start_time = time.time()
        captured: List[str] = []
        downloads_dir = Path(source_dir) if source_dir else FileManager._downloads_dir()
        default_downloads_dir = FileManager._downloads_dir()

        def _list_complete_files(base_dir: Path) -> List[str]:
            files = glob.glob(str(base_dir / pattern))
            excluded = exclude_paths or set()
            return [
                f for f in files
                if (
                    os.path.isfile(f)
                    and not f.endswith((".crdownload", ".tmp", ".part"))
                    and (
                        os.path.abspath(f) not in excluded
                        or (
                            min_modified_time is not None
                            and os.path.getmtime(f) >= min_modified_time
                        )
                        or (
                            preexisting_signatures is not None
                            and (
                                FileManager._file_signature(f)
                                != preexisting_signatures.get(os.path.abspath(f))
                            )
                        )
                    )
                    and (
                        min_modified_time is None
                        or os.path.getmtime(f) >= min_modified_time
                    )
                )
            ]

        while time.time() - start_time < timeout_seconds:
            complete_files = _list_complete_files(downloads_dir)

            # Fallback for remote Selenium nodes that ignore run-specific folder.
            if (
                not complete_files
                and source_dir
                and downloads_dir.resolve() != default_downloads_dir.resolve()
            ):
                complete_files = _list_complete_files(default_downloads_dir)

            if complete_files:
                run_dir = FileManager._artifacts_dir() / run_id / "original"
                run_dir.mkdir(parents=True, exist_ok=True)

                for found_file in sorted(complete_files):
                    filename = os.path.basename(found_file)
                    dest_path = run_dir / filename
                    try:
                        shutil.move(found_file, dest_path)
                        captured.append(str(dest_path))
                        logger.info(f"Captured file: {filename} -> {dest_path}")
                    except Exception as e:
                        logger.error(f"Failed to move file {found_file}: {e}")
                break

            time.sleep(1)

        if not captured:
            logger.warning(f"No files matching '{pattern}' found in {downloads_dir} after {timeout_seconds}s")

        return captured

    @staticmethod
    def rename_file(file_path: str, metadata: Dict[str, str], suffix: str = "") -> Optional[str]:
        """
        Rename file according to standard convention: Bank-Account-DDMMYYYY.xlsx

        Args:
            file_path: Path to file to rename
            metadata: Dict with 'bank', 'account', 'date' keys
            suffix: Optional suffix to avoid collisions (e.g. "2")

        Returns:
            New file path, or None if failed
        """
        try:
            path = Path(file_path)

            bank = FileManager._safe_component(metadata.get("bank", "Unknown"), "Unknown")
            account = FileManager._safe_component(metadata.get("account", "0000"), "0000")
            date_str = FileManager._safe_component(
                metadata.get("date", datetime.now().strftime("%d%m%Y")),
                datetime.now().strftime("%d%m%Y"),
            )
            suffix = FileManager._safe_component(suffix, "")

            extension = path.suffix
            base_name = f"{bank}-{account}-{date_str}"
            if suffix:
                base_name = f"{base_name}-{suffix}"
            new_filename = f"{base_name}{extension}"
            new_path = path.parent / new_filename

            counter = 1
            while new_path.exists() and new_path != path:
                new_path = path.parent / f"{base_name}-{counter}{extension}"
                counter += 1

            path.rename(new_path)
            logger.info(f"Renamed: {path.name} -> {new_path.name}")
            return str(new_path)

        except Exception as e:
            logger.error(f"Failed to rename file {file_path}: {e}")
            return None

    @staticmethod
    def process_file(original_path: str, run_id: str, metadata: Dict[str, str], suffix: str = "") -> Optional[str]:
        """
        Process file into standardized format.
        Currently a placeholder - copies file to processed directory with standardized name.

        Args:
            original_path: Path to original file
            run_id: Run ID for organizing files

        Returns:
            Path to processed file, or None if failed
        """
        try:
            original = Path(original_path)

            processed_dir = FileManager._artifacts_dir() / run_id / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)

            bank = FileManager._safe_component(metadata.get("bank", "Unknown"), "Unknown")
            account = FileManager._safe_component(metadata.get("account", "0000"), "0000")
            date_str = FileManager._safe_component(
                metadata.get("date", datetime.now().strftime("%d%m%Y")),
                datetime.now().strftime("%d%m%Y"),
            )
            suffix = FileManager._safe_component(suffix, "")
            extension = original.suffix
            base_name = f"{bank}-{account}-{date_str}"
            if suffix:
                base_name = f"{base_name}-{suffix}"
            processed_name = f"{base_name}{extension}"

            processed_path = processed_dir / processed_name
            counter = 1
            while processed_path.exists():
                processed_path = processed_dir / f"{base_name}-{counter}{extension}"
                counter += 1

            shutil.copy2(original, processed_path)

            logger.info(f"Processed file: {original.name} -> {processed_path}")
            return str(processed_path)

        except Exception as e:
            logger.error(f"Failed to process file {original_path}: {e}")
            return None

    @staticmethod
    def get_file_size(file_path: str) -> Optional[int]:
        """Get file size in bytes."""
        try:
            return os.path.getsize(file_path)
        except Exception:
            return None

    @staticmethod
    def list_run_files(run_id: str) -> List[Dict[str, str]]:
        """
        List all files for a specific run.

        Args:
            run_id: Run ID

        Returns:
            List of file metadata dicts
        """
        files = []
        run_dir = FileManager._artifacts_dir() / run_id

        if not run_dir.exists():
            return files

        original_dir = run_dir / "original"
        if original_dir.exists():
            for file_path in original_dir.glob("*"):
                if file_path.is_file():
                    files.append(
                        {
                            "file_type": "original",
                            "filename": file_path.name,
                            "path": file_path.relative_to(FileManager._artifacts_dir()).as_posix(),
                            "size_bytes": file_path.stat().st_size,
                            "status": "ready",
                        }
                    )

        processed_dir = run_dir / "processed"
        if processed_dir.exists():
            for file_path in processed_dir.glob("*"):
                if file_path.is_file():
                    files.append(
                        {
                            "file_type": "processed",
                            "filename": file_path.name,
                            "path": file_path.relative_to(FileManager._artifacts_dir()).as_posix(),
                            "size_bytes": file_path.stat().st_size,
                            "status": "ready",
                        }
                    )

        return files
