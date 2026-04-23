from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import ntpath
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Literal, Sequence
from uuid import uuid4
import zipfile


_SAFE_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._ -]+")
_ALLOWLIST_SPLIT_PATTERN = re.compile(r"[;,\n]+")
_DOCKER_CONTAINER_COMPONENT_PATTERN = re.compile(r"[^a-z0-9_.-]+")

SandboxMode = Literal["none", "docker"]


@dataclass(frozen=True)
class UploadedArtifact:
    relative_path: str
    content: bytes


@dataclass(frozen=True)
class FolderExecutionSummary:
    folder_name: str
    script_name: str
    input_files: list[str]
    output_files: list[str]
    stdout: str
    stderr: str


@dataclass(frozen=True)
class AutomatedProcessingResult:
    archive_path: Path
    working_dir: Path
    folders: list[FolderExecutionSummary]
    folder_statuses: list[dict[str, str]]


@dataclass(frozen=True)
class SandboxHealthResult:
    ready: bool
    sandbox_mode: SandboxMode
    docker_available: bool
    image: str
    image_pull_ok: bool
    docker_version: str | None
    message: str


class AutomatedProcessingError(Exception):
    def __init__(self, message: str, details: list[dict[str, str]] | None = None):
        super().__init__(message)
        self.details = details or []


def _docker_health_timeout_seconds() -> int:
    raw = (os.getenv("AUTOMATED_PROCESSING_SANDBOX_HEALTH_TIMEOUT", "600") or "600").strip()
    try:
        parsed = int(raw)
    except ValueError:
        return 600
    return max(10, min(parsed, 3600))


def _docker_image_exists(*, docker_binary: str, image: str, timeout_seconds: int) -> bool:
    try:
        inspect_result = subprocess.run(
            [docker_binary, "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AutomatedProcessingError(
            f"Timeout ao validar imagem Docker local '{image}' ({timeout_seconds}s)."
        ) from exc

    return inspect_result.returncode == 0


def _parse_sandbox_mode(raw_mode: str) -> SandboxMode:
    normalized = (raw_mode or "none").strip().lower()
    if normalized in {"", "none", "local"}:
        return "none"
    if normalized == "docker":
        return "docker"
    raise AutomatedProcessingError(
        f"sandbox_mode invalido: {raw_mode}. Valores aceitos: none, docker."
    )


def _build_sandbox_container_name(context: str) -> str:
    normalized_context = (context or "folder").strip().lower()
    normalized_context = _DOCKER_CONTAINER_COMPONENT_PATTERN.sub("-", normalized_context)
    normalized_context = normalized_context.strip("-.")
    if not normalized_context:
        normalized_context = "folder"

    normalized_context = normalized_context[:32].rstrip("-.") or "folder"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    nonce = uuid4().hex[:8]
    return f"beehus-sandbox-{normalized_context}-{timestamp}-{nonce}"


def _docker_hardening_flags() -> list[str]:
    return [
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
    ]


def _truncate_text(value: str, limit: int = 240) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _format_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _probe_execution_diagnostic(
    *,
    stage: str,
    command: Sequence[str],
    returncode: int,
    stdout: str,
    stderr: str,
) -> str:
    return (
        f"{stage}: rc={returncode}; cmd={_format_command(command)}; "
        f"stdout={_truncate_text(stdout)}; stderr={_truncate_text(stderr)}"
    )


def _is_python_exec_permission_error(detail: str) -> bool:
    lowered = (detail or "").lower()
    if "operation not permitted" not in lowered:
        return False

    return (
        "exec /usr/local/bin/python" in lowered
        or 'exec "/usr/local/bin/python"' in lowered
        or "exec: \"python\"" in lowered
        or "exec: python" in lowered
    )


def validate_sandbox_health(
    *,
    sandbox_mode: str,
    pull_image: bool = True,
    run_probe: bool = False,
    timeout_seconds: int | None = None,
) -> SandboxHealthResult:
    mode = _parse_sandbox_mode(sandbox_mode)
    image = _docker_image()

    if mode == "none":
        return SandboxHealthResult(
            ready=True,
            sandbox_mode=mode,
            docker_available=False,
            image=image,
            image_pull_ok=False,
            docker_version=None,
            message="Sandbox desativado (modo local).",
        )

    docker_binary = shutil.which("docker")
    if not docker_binary:
        raise AutomatedProcessingError(
            "Sandbox Docker solicitado, mas o comando 'docker' nao esta disponivel no servidor."
        )

    effective_timeout = timeout_seconds if timeout_seconds is not None else _docker_health_timeout_seconds()
    if effective_timeout < 10:
        effective_timeout = 10

    try:
        version_result = subprocess.run(
            [docker_binary, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AutomatedProcessingError(
            f"Timeout ao validar Docker no health-check de sandbox ({effective_timeout}s)."
        ) from exc

    docker_version = (version_result.stdout or "").strip() or None
    if version_result.returncode != 0:
        stderr = (version_result.stderr or "").strip()
        message = stderr or "Falha ao executar docker version."
        raise AutomatedProcessingError(f"Docker indisponivel para sandbox: {message}")

    message = "Sandbox Docker validado com sucesso."
    image_pull_ok = False
    if pull_image:
        try:
            pull_result = subprocess.run(
                [docker_binary, "pull", image],
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AutomatedProcessingError(
                f"Timeout ao executar docker pull da imagem '{image}' ({effective_timeout}s)."
            ) from exc

        if pull_result.returncode != 0:
            stderr = (pull_result.stderr or "").strip()
            message = stderr or "Falha ao executar docker pull."
            local_image_found = _docker_image_exists(
                docker_binary=docker_binary,
                image=image,
                timeout_seconds=effective_timeout,
            )
            if not local_image_found:
                raise AutomatedProcessingError(
                    f"Health-check sandbox falhou ao baixar imagem '{image}': {message}"
                )
            message = (
                f"Sandbox Docker validado usando imagem local '{image}' "
                f"(docker pull falhou: {message})."
            )
        else:
            image_pull_ok = True
    else:
        local_image_found = _docker_image_exists(
            docker_binary=docker_binary,
            image=image,
            timeout_seconds=effective_timeout,
        )
        if not local_image_found:
            raise AutomatedProcessingError(
                f"Imagem Docker '{image}' nao encontrada localmente. "
                "Faca build/pull da imagem ou habilite pull_image=true no health-check."
            )
        message = f"Sandbox Docker validado com imagem local '{image}'."

    if run_probe:
        probe_container_name = _build_sandbox_container_name("health")
        probe_base_command = [
            docker_binary,
            "run",
            "--rm",
            "--name",
            probe_container_name,
            "--network",
            "none",
            "--cpus",
            _docker_cpu_limit(),
            "--memory",
            _docker_memory_limit(),
            "--pids-limit",
            _docker_pids_limit(),
        ]

        probe_command = probe_base_command + _docker_hardening_flags() + [image, "python", "-V"]
        try:
            probe_result = subprocess.run(
                probe_command,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AutomatedProcessingError(
                f"Timeout ao executar probe Docker da imagem '{image}' ({effective_timeout}s)."
            ) from exc

        if probe_result.returncode != 0:
            probe_stdout = (probe_result.stdout or "").strip()
            probe_stderr = (probe_result.stderr or "").strip()
            probe_detail = (probe_stderr or probe_stdout).strip()
            if not probe_detail:
                probe_detail = f"codigo de saida {probe_result.returncode}"
            strict_diag = _probe_execution_diagnostic(
                stage="strict",
                command=probe_command,
                returncode=probe_result.returncode,
                stdout=probe_stdout,
                stderr=probe_stderr,
            )
            if _is_python_exec_permission_error(probe_detail):
                relaxed_probe_command = probe_base_command + [image, "python", "-V"]
                try:
                    relaxed_probe_result = subprocess.run(
                        relaxed_probe_command,
                        capture_output=True,
                        text=True,
                        timeout=effective_timeout,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise AutomatedProcessingError(
                        "Health-check sandbox falhou no fallback sem hardening da imagem "
                        f"'{image}' por timeout ({effective_timeout}s)."
                    ) from exc

                if relaxed_probe_result.returncode != 0:
                    relaxed_stdout = (relaxed_probe_result.stdout or "").strip()
                    relaxed_stderr = (relaxed_probe_result.stderr or "").strip()
                    relaxed_detail = (relaxed_stderr or relaxed_stdout).strip()
                    if not relaxed_detail:
                        relaxed_detail = f"codigo de saida {relaxed_probe_result.returncode}"
                    relaxed_diag = _probe_execution_diagnostic(
                        stage="relaxed",
                        command=relaxed_probe_command,
                        returncode=relaxed_probe_result.returncode,
                        stdout=relaxed_stdout,
                        stderr=relaxed_stderr,
                    )
                    raise AutomatedProcessingError(
                        "Health-check sandbox falhou no probe de execucao da imagem "
                        f"'{image}' (modo hardening e fallback sem hardening): {relaxed_detail}. "
                        f"Diagnostico: {strict_diag} | {relaxed_diag}"
                    )

                probe_output = (relaxed_probe_result.stdout or relaxed_probe_result.stderr or "").strip()
                if probe_output:
                    message = (
                        f"{message} Probe de execucao OK ({probe_output}) com fallback sem hardening "
                        "(host bloqueou execucao Python com politicas restritas)."
                    )
                else:
                    message = (
                        f"{message} Probe de execucao OK com fallback sem hardening "
                        "(host bloqueou execucao Python com politicas restritas)."
                    )
            else:
                raise AutomatedProcessingError(
                    "Health-check sandbox falhou no probe de execucao da imagem "
                    f"'{image}': {probe_detail}. Diagnostico: {strict_diag}"
                )

        elif "fallback sem hardening" not in message:
            probe_output = (probe_result.stdout or probe_result.stderr or "").strip()
            if probe_output:
                message = f"{message} Probe de execucao OK ({probe_output})."
            else:
                message = f"{message} Probe de execucao OK."

    return SandboxHealthResult(
        ready=True,
        sandbox_mode=mode,
        docker_available=True,
        image=image,
        image_pull_ok=image_pull_ok,
        docker_version=docker_version,
        message=message,
    )


def _sanitize_component(value: str) -> str:
    cleaned = _SAFE_COMPONENT_PATTERN.sub("_", value).strip(" ._")
    return cleaned or "folder"


def _unique_folder_name(preferred: str, used: set[str]) -> str:
    if preferred not in used:
        used.add(preferred)
        return preferred

    index = 2
    while True:
        candidate = f"{preferred}_{index}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def _normalize_relative_path(raw_path: str) -> PurePosixPath:
    normalized = (raw_path or "").strip().replace("\\", "/").lstrip("/")
    if not normalized:
        raise AutomatedProcessingError("Arquivo recebido sem caminho relativo.")

    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise AutomatedProcessingError(f"Caminho invalido recebido: {raw_path}")

    if len(path.parts) == 1:
        return PurePosixPath("folder") / path

    return path


def _split_allowlist(raw_value: str) -> list[str]:
    if not raw_value.strip():
        return []
    return [chunk.strip() for chunk in _ALLOWLIST_SPLIT_PATTERN.split(raw_value) if chunk.strip()]


def _server_allowlist_roots() -> list[Path]:
    raw_value = os.getenv("AUTOMATED_PROCESSING_SERVER_ALLOWLIST", "")
    candidates = _split_allowlist(raw_value)
    roots: list[Path] = []
    for candidate in candidates:
        root = Path(candidate).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            continue
        roots.append(root)
    return roots


def _is_child_of(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_server_folder(path_value: str, allowlist_roots: Sequence[Path]) -> Path:
    raw = (path_value or "").strip()
    if not raw:
        raise AutomatedProcessingError("Um caminho de pasta no servidor foi enviado vazio.")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise AutomatedProcessingError(
            f"Caminho de pasta deve ser absoluto para modo servidor: {raw}"
        )

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise AutomatedProcessingError(f"Pasta nao encontrada no servidor: {raw}") from exc

    if not resolved.is_dir():
        raise AutomatedProcessingError(f"Caminho nao e uma pasta valida: {raw}")

    if not any(_is_child_of(resolved, root) for root in allowlist_roots):
        raise AutomatedProcessingError(
            "Pasta fora da allowlist de seguranca configurada para processamento por caminho."
        )

    return resolved


def _materialize_artifacts(
    artifacts: Sequence[UploadedArtifact],
    uploads_root: Path,
) -> dict[str, Path]:
    used_names: set[str] = set()
    source_to_target: dict[str, str] = {}
    folders: dict[str, Path] = {}

    for artifact in artifacts:
        normalized_path = _normalize_relative_path(artifact.relative_path)
        source_folder = normalized_path.parts[0]
        folder_name = source_to_target.get(source_folder)
        if folder_name is None:
            folder_name = _unique_folder_name(_sanitize_component(source_folder), used_names)
            source_to_target[source_folder] = folder_name
            folder_path = uploads_root / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
            folders[folder_name] = folder_path

        relative_inside_folder = PurePosixPath(*normalized_path.parts[1:])
        target_path = folders[folder_name] / Path(relative_inside_folder.as_posix())
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists():
            raise AutomatedProcessingError(
                f"Arquivo duplicado recebido para a pasta {folder_name}: {relative_inside_folder.as_posix()}"
            )

        target_path.write_bytes(artifact.content)

    return folders


def _materialize_server_folders(
    folder_paths: Sequence[str],
    uploads_root: Path,
    *,
    write_to_source: bool = False,
) -> dict[str, Path]:
    allowlist_roots = _server_allowlist_roots()
    if not allowlist_roots:
        raise AutomatedProcessingError(
            "Modo por caminho no servidor esta desabilitado: configure allowlist explicita para habilitar."
        )

    used_names: set[str] = set()
    folders: dict[str, Path] = {}

    for path_value in folder_paths:
        source_folder = _validate_server_folder(path_value, allowlist_roots)
        folder_name = _unique_folder_name(_sanitize_component(source_folder.name), used_names)
        if write_to_source:
            folders[folder_name] = source_folder
        else:
            target_folder = uploads_root / folder_name
            shutil.copytree(source_folder, target_folder)
            folders[folder_name] = target_folder

    return folders


def _should_ignore_path(path: PurePosixPath) -> bool:
    if "__pycache__" in path.parts:
        return True
    return path.suffix.lower() in {".py", ".pyc"}


def _snapshot_non_python_files(folder_path: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for candidate in folder_path.iterdir():
        if not candidate.is_file():
            continue
        relative = PurePosixPath(candidate.relative_to(folder_path).as_posix())
        if _should_ignore_path(relative):
            continue
        stat = candidate.stat()
        snapshot[relative.as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _find_single_python_script(folder_path: Path, folder_name: str) -> Path:
    scripts: list[Path] = []
    for candidate in folder_path.iterdir():
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() != ".py":
            continue
        relative = PurePosixPath(candidate.relative_to(folder_path).as_posix())
        if "__pycache__" in relative.parts:
            continue
        scripts.append(candidate)

    if not scripts:
        raise AutomatedProcessingError(
            f"Pasta {folder_name} nao possui arquivo .py de processamento na raiz da pasta (subpastas sao ignoradas)."
        )

    if len(scripts) > 1:
        names = ", ".join(sorted(path.relative_to(folder_path).as_posix() for path in scripts))
        raise AutomatedProcessingError(
            f"Pasta {folder_name} possui mais de um arquivo .py na raiz ({names}). Deixe apenas um script .py na raiz da pasta."
        )

    return scripts[0]


def _copy_outputs(
    folder_name: str,
    folder_path: Path,
    changed_files: list[str],
    outputs_root: Path,
) -> list[str]:
    copied: list[str] = []
    output_folder = outputs_root / folder_name

    for relative_file in changed_files:
        source = folder_path / Path(relative_file)
        target = output_folder / Path(relative_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append((Path(folder_name) / Path(relative_file)).as_posix())

    return copied


def _script_failure_hint(error_detail: str) -> str:
    lowered = error_detail.lower()
    if (
        "exec /usr/local/bin/python" in lowered
        and "operation not permitted" in lowered
    ):
        return (
            " Dica: o sandbox Docker iniciou, mas a execucao do binario Python foi "
            "bloqueada pelo runtime do host. Isso geralmente indica politica de "
            "seguranca do ambiente (seccomp/apparmor/noexec) ou imagem sandbox "
            "invalida/corrompida. Valide no host: primeiro execute a imagem sem "
            "hardening (docker run --rm <imagem> python -V) e depois repita com "
            "os mesmos flags de sandbox aplicados pelo Beehus."
        )

    if (
        "conditional_formatting.add" in lowered
        and (
            "1 must be greater than 2" in lowered
            or "multicellrange" in lowered
            or "cellrange" in lowered
        )
    ):
        return (
            " Dica: o script tentou aplicar formatacao condicional em um intervalo "
            "invalido (ex.: A2:A1). Antes de chamar conditional_formatting.add, "
            "valide se a faixa possui linhas de dados (linha inicial <= final), "
            "por exemplo: start_row = 2; end_row = max_row; "
            "if end_row >= start_row: ws.conditional_formatting.add(...)"
        )
    return ""


def _docker_image() -> str:
    configured = os.getenv("AUTOMATED_PROCESSING_SANDBOX_IMAGE", "").strip()
    if configured:
        return configured
    return "beehus-automated-processing-sandbox:latest"


def _docker_memory_limit() -> str:
    configured = os.getenv("AUTOMATED_PROCESSING_SANDBOX_MEMORY", "").strip()
    return configured or "512m"


def _docker_cpu_limit() -> str:
    configured = os.getenv("AUTOMATED_PROCESSING_SANDBOX_CPUS", "").strip()
    return configured or "1.0"


def _docker_pids_limit() -> str:
    configured = os.getenv("AUTOMATED_PROCESSING_SANDBOX_PIDS_LIMIT", "").strip()
    return configured or "128"


def _execution_wrapper_code() -> str:
    # Compatibility shim: some user scripts build conditional-format ranges
    # even when there are no data rows (e.g., A2:A1). We ignore only this
    # known openpyxl range-conversion failure to keep user scripts runnable.
    return (
        "import runpy, sys\n"
        "try:\n"
        "    from openpyxl.formatting.formatting import ConditionalFormattingList\n"
        "    _orig_add = ConditionalFormattingList.add\n"
        "    def _safe_add(self, range_string, cfRule):\n"
        "        try:\n"
        "            return _orig_add(self, range_string, cfRule)\n"
        "        except Exception as exc:\n"
        "            msg = str(exc)\n"
        "            if ('must be greater than' in msg) or ('MultiCellRange' in msg) or ('CellRange' in msg):\n"
        "                return None\n"
        "            raise\n"
        "    ConditionalFormattingList.add = _safe_add\n"
        "except Exception:\n"
        "    pass\n"
        "try:\n"
        "    import os\n"
        "    import pandas as _pd\n"
        "    _orig_read_excel = _pd.read_excel\n"
        "    _orig_excel_file = _pd.ExcelFile\n"
        "    def _looks_like_html_table(source):\n"
        "        try:\n"
        "            path = os.fspath(source)\n"
        "        except Exception:\n"
        "            return False\n"
        "        if not path:\n"
        "            return False\n"
        "        try:\n"
        "            with open(path, 'rb') as fh:\n"
        "                head = fh.read(2048)\n"
        "        except Exception:\n"
        "            return False\n"
        "        sample = head.lower()\n"
        "        return (b'<table' in sample) or (b'<html' in sample)\n"
        "    def _to_str_df(df, dtype):\n"
        "        if dtype is str:\n"
        "            try:\n"
        "                return df.astype(str)\n"
        "            except Exception:\n"
        "                return df\n"
        "        return df\n"
        "    def _pick_table(tables, sheet_name):\n"
        "        if not tables:\n"
        "            raise ValueError('No HTML tables found')\n"
        "        if isinstance(sheet_name, int):\n"
        "            if 0 <= sheet_name < len(tables):\n"
        "                return tables[sheet_name]\n"
        "            return tables[0]\n"
        "        if isinstance(sheet_name, str):\n"
        "            if sheet_name.lower().startswith('sheet'):\n"
        "                try:\n"
        "                    idx = int(sheet_name[5:]) - 1\n"
        "                    if 0 <= idx < len(tables):\n"
        "                        return tables[idx]\n"
        "                except Exception:\n"
        "                    pass\n"
        "            return tables[0]\n"
        "        return tables[0]\n"
        "    class _CompatExcelFile:\n"
        "        def __init__(self, io, *args, **kwargs):\n"
        "            self._wrapped = None\n"
        "            self._tables = None\n"
        "            try:\n"
        "                self._wrapped = _orig_excel_file(io, *args, **kwargs)\n"
        "                self.sheet_names = list(self._wrapped.sheet_names)\n"
        "            except Exception:\n"
        "                if not _looks_like_html_table(io):\n"
        "                    raise\n"
        "                self._tables = _pd.read_html(io, flavor='lxml')\n"
        "                self.sheet_names = [f'Sheet{i+1}' for i in range(len(self._tables))]\n"
        "        def parse(self, sheet_name=0, **kwargs):\n"
        "            if self._wrapped is not None:\n"
        "                return self._wrapped.parse(sheet_name=sheet_name, **kwargs)\n"
        "            dtype = kwargs.get('dtype')\n"
        "            table = _pick_table(self._tables or [], sheet_name)\n"
        "            return _to_str_df(table, dtype)\n"
        "        def close(self):\n"
        "            if self._wrapped is not None and hasattr(self._wrapped, 'close'):\n"
        "                self._wrapped.close()\n"
        "        def __enter__(self):\n"
        "            return self\n"
        "        def __exit__(self, exc_type, exc, tb):\n"
        "            self.close()\n"
        "    def _safe_read_excel(io, *args, **kwargs):\n"
        "        if isinstance(io, _CompatExcelFile):\n"
        "            sheet_name = kwargs.pop('sheet_name', 0)\n"
        "            if len(args) >= 1:\n"
        "                sheet_name = args[0]\n"
        "            return io.parse(sheet_name=sheet_name, **kwargs)\n"
        "        try:\n"
        "            return _orig_read_excel(io, *args, **kwargs)\n"
        "        except Exception:\n"
            "            if not _looks_like_html_table(io):\n"
            "                raise\n"
        "            sheet_name = kwargs.get('sheet_name', 0)\n"
        "            if len(args) >= 1:\n"
        "                sheet_name = args[0]\n"
        "            tables = _pd.read_html(io, flavor='lxml')\n"
        "            dtype = kwargs.get('dtype')\n"
        "            if isinstance(sheet_name, list):\n"
        "                out = {}\n"
        "                for sn in sheet_name:\n"
        "                    out[sn] = _to_str_df(_pick_table(tables, sn), dtype)\n"
        "                return out\n"
        "            table = _pick_table(tables, sheet_name)\n"
        "            return _to_str_df(table, dtype)\n"
        "    _pd.ExcelFile = _CompatExcelFile\n"
        "    _pd.read_excel = _safe_read_excel\n"
        "except Exception:\n"
        "    pass\n"
        "script = sys.argv[1]\n"
        "sys.argv = [script] + sys.argv[2:]\n"
        "runpy.run_path(script, run_name='__main__')\n"
    )


def _join_host_source_path(source: str, relative_posix: str) -> str:
    if not relative_posix:
        return source
    parts = [part for part in relative_posix.split("/") if part]
    if re.match(r"^[A-Za-z]:[\\/]", source):
        return ntpath.join(source, *parts)
    return posixpath.join(source, *parts)


def _resolve_docker_bind_source_path(
    *,
    local_path: Path,
    docker_binary: str,
    timeout_seconds: int,
) -> str:
    resolved_local = local_path.resolve()
    container_id = (os.getenv("HOSTNAME") or "").strip()
    if not container_id:
        return str(resolved_local)

    try:
        inspect_result = subprocess.run(
            [docker_binary, "inspect", container_id, "--format", "{{json .Mounts}}"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return str(resolved_local)

    if inspect_result.returncode != 0:
        return str(resolved_local)

    mounts_raw = (inspect_result.stdout or "").strip()
    if not mounts_raw:
        return str(resolved_local)

    try:
        mounts = json.loads(mounts_raw)
    except json.JSONDecodeError:
        return str(resolved_local)

    if not isinstance(mounts, list):
        return str(resolved_local)

    local_posix = PurePosixPath(resolved_local.as_posix())
    best_match_destination: PurePosixPath | None = None
    best_match_source: str | None = None

    for mount in mounts:
        if not isinstance(mount, dict):
            continue
        if mount.get("Type") != "bind":
            continue

        destination_raw = mount.get("Destination")
        source_raw = mount.get("Source")
        if not isinstance(destination_raw, str) or not isinstance(source_raw, str):
            continue

        destination = PurePosixPath(destination_raw)
        if local_posix == destination or str(local_posix).startswith(f"{destination}/"):
            if best_match_destination is None or len(str(destination)) > len(str(best_match_destination)):
                best_match_destination = destination
                best_match_source = source_raw

    if best_match_destination is None or best_match_source is None:
        return str(resolved_local)

    relative = ""
    if local_posix != best_match_destination:
        relative = str(local_posix.relative_to(best_match_destination))

    return _join_host_source_path(best_match_source, relative)


def _create_processing_working_dir(*, prefix: str, sandbox_mode: SandboxMode) -> Path:
    if sandbox_mode == "docker":
        docker_tmp_root = Path("/app/.sandbox_tmp")
        try:
            docker_tmp_root.mkdir(parents=True, exist_ok=True)
            return Path(tempfile.mkdtemp(prefix=prefix, dir=str(docker_tmp_root)))
        except OSError:
            pass
    return Path(tempfile.mkdtemp(prefix=prefix))


def _run_folder_command(
    *,
    folder_name: str,
    folder_path: Path,
    script_relative: str,
    timeout_seconds: int,
    sandbox_mode: SandboxMode,
) -> subprocess.CompletedProcess[str]:
    try:
        wrapper_code = _execution_wrapper_code()

        if sandbox_mode == "none":
            return subprocess.run(
                [sys.executable, "-B", "-c", wrapper_code, script_relative],
                cwd=str(folder_path),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )

        docker_binary = shutil.which("docker")
        if not docker_binary:
            raise AutomatedProcessingError(
                "Sandbox Docker solicitado, mas o comando 'docker' nao esta disponivel no servidor."
            )

        bind_source_path = _resolve_docker_bind_source_path(
            local_path=folder_path,
            docker_binary=docker_binary,
            timeout_seconds=timeout_seconds,
        )
        sandbox_container_name = _build_sandbox_container_name(folder_name)

        docker_base_command = [
            docker_binary,
            "run",
            "--rm",
            "--name",
            sandbox_container_name,
            "--network",
            "none",
            "--cpus",
            _docker_cpu_limit(),
            "--memory",
            _docker_memory_limit(),
            "--pids-limit",
            _docker_pids_limit(),
            "--mount",
            f"type=bind,src={bind_source_path},dst=/work",
            "--workdir",
            "/work",
        ]
        docker_exec_args = [_docker_image(), "python", "-I", "-B", "-c", wrapper_code, script_relative]

        strict_command = docker_base_command + _docker_hardening_flags() + docker_exec_args
        strict_result = subprocess.run(
            strict_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if strict_result.returncode == 0:
            return strict_result

        strict_detail = (strict_result.stderr or strict_result.stdout or "").strip()
        if not _is_python_exec_permission_error(strict_detail):
            return strict_result

        relaxed_command = docker_base_command + docker_exec_args
        return subprocess.run(
            relaxed_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        mode_name = "sandbox Docker" if sandbox_mode == "docker" else "execucao local"
        raise AutomatedProcessingError(
            f"Script da pasta {folder_name} excedeu timeout de {timeout_seconds} segundos ({mode_name})."
        ) from exc


def _execute_folder_script(
    *,
    folder_name: str,
    folder_path: Path,
    outputs_root: Path,
    timeout_seconds: int,
    sandbox_mode: SandboxMode,
) -> FolderExecutionSummary:
    script_path = _find_single_python_script(folder_path, folder_name)
    initial_snapshot = _snapshot_non_python_files(folder_path)

    if not initial_snapshot:
        raise AutomatedProcessingError(f"Pasta {folder_name} nao possui arquivos de input para processar.")

    script_relative = script_path.relative_to(folder_path).as_posix()
    completed = _run_folder_command(
        folder_name=folder_name,
        folder_path=folder_path,
        script_relative=script_relative,
        timeout_seconds=timeout_seconds,
        sandbox_mode=sandbox_mode,
    )

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        error_detail = stderr or stdout or f"Codigo de saida {completed.returncode}"
        hint = _script_failure_hint(error_detail)
        raise AutomatedProcessingError(
            f"Script da pasta {folder_name} falhou com codigo {completed.returncode}: {error_detail}{hint}"
        )

    final_snapshot = _snapshot_non_python_files(folder_path)
    changed_files: list[str] = []
    for relative_file, final_metadata in final_snapshot.items():
        initial_metadata = initial_snapshot.get(relative_file)
        if initial_metadata is None or initial_metadata != final_metadata:
            changed_files.append(relative_file)

    if not changed_files:
        raise AutomatedProcessingError(
            f"Script da pasta {folder_name} executou, mas nenhum arquivo de saida foi gerado ou alterado."
        )

    changed_files.sort()
    copied_outputs = _copy_outputs(folder_name, folder_path, changed_files, outputs_root)

    return FolderExecutionSummary(
        folder_name=folder_name,
        script_name=script_relative,
        input_files=sorted(initial_snapshot.keys()),
        output_files=copied_outputs,
        stdout=stdout,
        stderr=stderr,
    )


def _build_archive(
    *,
    archive_path: Path,
    outputs_root: Path,
    summaries: list[FolderExecutionSummary],
    folder_statuses: list[dict[str, str]],
) -> None:
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for output_path in outputs_root.rglob("*"):
            if not output_path.is_file():
                continue
            zip_file.write(output_path, arcname=output_path.relative_to(outputs_root).as_posix())

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "folders": [
                {
                    "folder_name": summary.folder_name,
                    "status": "success",
                    "script_name": summary.script_name,
                    "input_files": summary.input_files,
                    "output_files": summary.output_files,
                    "stdout": summary.stdout,
                    "stderr": summary.stderr,
                }
                for summary in summaries
            ],
            "folder_statuses": folder_statuses,
        }
        zip_file.writestr("processing_report.json", json.dumps(report, ensure_ascii=True, indent=2))


def _process_materialized_folders(
    *,
    working_dir: Path,
    folders: dict[str, Path],
    timeout_seconds: int,
    sandbox_mode: SandboxMode,
) -> AutomatedProcessingResult:
    outputs_root = working_dir / "outputs"
    outputs_root.mkdir(parents=True, exist_ok=True)

    failures: list[dict[str, str]] = []
    summaries: list[FolderExecutionSummary] = []
    folder_statuses: list[dict[str, str]] = []

    for folder_name, folder_path in folders.items():
        try:
            summary = _execute_folder_script(
                folder_name=folder_name,
                folder_path=folder_path,
                outputs_root=outputs_root,
                timeout_seconds=timeout_seconds,
                sandbox_mode=sandbox_mode,
            )
            summaries.append(summary)
            folder_statuses.append(
                {
                    "folder": folder_name,
                    "status": "success",
                    "error": "",
                }
            )
        except AutomatedProcessingError as exc:
            error_message = str(exc)
            status_item = {
                "folder": folder_name,
                "status": "failed",
                "error": error_message,
            }
            failures.append(status_item)
            folder_statuses.append(status_item)

    if failures and not summaries:
        raise AutomatedProcessingError("Falha ao processar uma ou mais pastas.", details=folder_statuses)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_path = working_dir / f"processamento_automatizado_{timestamp}.zip"
    _build_archive(
        archive_path=archive_path,
        outputs_root=outputs_root,
        summaries=summaries,
        folder_statuses=folder_statuses,
    )

    return AutomatedProcessingResult(
        archive_path=archive_path,
        working_dir=working_dir,
        folders=summaries,
        folder_statuses=folder_statuses,
    )


def run_folder_processing_batch(
    artifacts: Sequence[UploadedArtifact],
    *,
    timeout_seconds: int = 300,
    sandbox_mode: str = "none",
) -> AutomatedProcessingResult:
    if not artifacts:
        raise AutomatedProcessingError("Selecione ao menos uma pasta com arquivos.")

    resolved_sandbox_mode = _parse_sandbox_mode(sandbox_mode)
    if resolved_sandbox_mode == "docker":
        validate_sandbox_health(sandbox_mode="docker", pull_image=True)

    working_dir = _create_processing_working_dir(
        prefix="beehus_auto_processing_",
        sandbox_mode=resolved_sandbox_mode,
    )
    uploads_root = working_dir / "uploads"
    uploads_root.mkdir(parents=True, exist_ok=True)

    try:
        folders = _materialize_artifacts(artifacts, uploads_root)
        if not folders:
            raise AutomatedProcessingError("Nao foi possivel identificar nenhuma pasta valida.")
        return _process_materialized_folders(
            working_dir=working_dir,
            folders=folders,
            timeout_seconds=timeout_seconds,
            sandbox_mode=resolved_sandbox_mode,
        )
    except Exception:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise


def run_server_path_processing_batch(
    folder_paths: Sequence[str],
    *,
    timeout_seconds: int = 300,
    sandbox_mode: str = "none",
    write_to_source: bool = False,
) -> AutomatedProcessingResult:
    if not folder_paths:
        raise AutomatedProcessingError("Selecione ao menos um caminho de pasta no servidor.")

    resolved_sandbox_mode = _parse_sandbox_mode(sandbox_mode)
    if resolved_sandbox_mode == "docker":
        validate_sandbox_health(sandbox_mode="docker", pull_image=True)

    working_dir = _create_processing_working_dir(
        prefix="beehus_auto_processing_server_",
        sandbox_mode=resolved_sandbox_mode,
    )
    uploads_root = working_dir / "uploads"
    uploads_root.mkdir(parents=True, exist_ok=True)

    try:
        folders = _materialize_server_folders(
            folder_paths,
            uploads_root,
            write_to_source=write_to_source,
        )
        if not folders:
            raise AutomatedProcessingError("Nao foi possivel identificar nenhuma pasta valida.")

        return _process_materialized_folders(
            working_dir=working_dir,
            folders=folders,
            timeout_seconds=timeout_seconds,
            sandbox_mode=resolved_sandbox_mode,
        )
    except Exception:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise
