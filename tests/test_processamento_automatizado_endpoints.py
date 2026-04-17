from io import BytesIO
from pathlib import Path
import tempfile
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.console.routers import processamento_automatizado
from core.services.automated_folder_processor import (
    AutomatedProcessingResult,
    FolderExecutionSummary,
    SandboxHealthResult,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(processamento_automatizado.router)
    return TestClient(app)


def test_processamento_automatizado_processa_pasta_e_retorna_zip():
    client = _client()

    script = """
from pathlib import Path

Path('resultado_processado.csv').write_text('coluna\\nok\\n', encoding='utf-8')
""".strip()

    files = [
        (
            "files",
            (
                "teste_kim/input_a.xlsx",
                b"conteudo_a",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
        (
            "files",
            (
                "teste_kim/input_b.xlsx",
                b"conteudo_b",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
        (
            "files",
            (
                "teste_kim/processamento.py",
                script.encode("utf-8"),
                "text/x-python",
            ),
        ),
    ]

    response = client.post("/processamento-automatizado/process", files=files)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    archive = ZipFile(BytesIO(response.content))
    names = set(archive.namelist())
    assert "processing_report.json" in names
    assert "teste_kim/resultado_processado.csv" in names

    report = archive.read("processing_report.json").decode("utf-8")
    assert '"folder": "teste_kim"' in report
    assert '"status": "success"' in report


def test_processamento_automatizado_download_auto_retorna_arquivo_unico(monkeypatch):
    client = _client()

    with tempfile.TemporaryDirectory(prefix="test_auto_proc_") as tmp_dir:
        work_dir = Path(tmp_dir) / "work"
        output_file = work_dir / "outputs" / "folder" / "resultado.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("coluna\n1\n", encoding="utf-8")

        archive_path = work_dir / "resultado.zip"
        archive_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

        def fake_run(artifacts, timeout_seconds=300, sandbox_mode="none"):
            return AutomatedProcessingResult(
                archive_path=archive_path,
                working_dir=work_dir,
                folders=[
                    FolderExecutionSummary(
                        folder_name="folder",
                        script_name="processamento.py",
                        input_files=["input.xlsx"],
                        output_files=["folder/resultado.csv"],
                        stdout="",
                        stderr="",
                    )
                ],
                folder_statuses=[{"folder": "folder", "status": "success", "error": ""}],
            )

        monkeypatch.setattr(processamento_automatizado, "run_folder_processing_batch", fake_run)

        files = [
            ("files", ("folder/input.xlsx", b"conteudo", "application/octet-stream")),
            ("files", ("folder/processamento.py", b"print('ok')", "text/x-python")),
        ]

        response = client.post(
            "/processamento-automatizado/process?download_mode=auto",
            files=files,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] != "application/zip"
        assert 'filename="resultado.csv"' in response.headers["content-disposition"]
        assert response.content.decode("utf-8").replace("\r\n", "\n") == "coluna\n1\n"


def test_processamento_automatizado_download_single_rejeita_multiplos_outputs(monkeypatch):
    client = _client()

    with tempfile.TemporaryDirectory(prefix="test_auto_proc_") as tmp_dir:
        work_dir = Path(tmp_dir) / "work"
        work_dir.mkdir(parents=True)
        archive_path = work_dir / "resultado.zip"
        archive_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

        def fake_run(artifacts, timeout_seconds=300, sandbox_mode="none"):
            return AutomatedProcessingResult(
                archive_path=archive_path,
                working_dir=work_dir,
                folders=[
                    FolderExecutionSummary(
                        folder_name="folder",
                        script_name="processamento.py",
                        input_files=["input.xlsx"],
                        output_files=["folder/saida_a.csv", "folder/saida_b.csv"],
                        stdout="",
                        stderr="",
                    )
                ],
                folder_statuses=[{"folder": "folder", "status": "success", "error": ""}],
            )

        monkeypatch.setattr(processamento_automatizado, "run_folder_processing_batch", fake_run)

        files = [
            ("files", ("folder/input.xlsx", b"conteudo", "application/octet-stream")),
            ("files", ("folder/processamento.py", b"print('ok')", "text/x-python")),
        ]

        response = client.post(
            "/processamento-automatizado/process?download_mode=single",
            files=files,
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert isinstance(detail, str)
        assert "sem compactacao" in detail.lower()


def test_processamento_automatizado_retorna_erro_sem_script_python():
    client = _client()

    files = [
        (
            "files",
            (
                "pasta_sem_script/input_a.xlsx",
                b"conteudo_a",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
    ]

    response = client.post("/processamento-automatizado/process", files=files)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["message"] == "Falha ao processar uma ou mais pastas."
    assert detail["errors"][0]["folder"] == "pasta_sem_script"
    assert detail["errors"][0]["status"] == "failed"


def test_processamento_automatizado_por_caminho_servidor(monkeypatch):
    client = _client()

    with tempfile.TemporaryDirectory(prefix="test_auto_proc_") as tmp_dir:
        base = Path(tmp_dir)
        allowed_root = base / "allow"
        folder = allowed_root / "teste_kim"
        folder.mkdir(parents=True)
        (folder / "input.xlsx").write_bytes(b"input")
        (folder / "processamento.py").write_text(
            "from pathlib import Path\nPath('resultado.csv').write_text('ok\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("AUTOMATED_PROCESSING_SERVER_ALLOWLIST", str(allowed_root))

        response = client.post(
            "/processamento-automatizado/process-server-paths",
            json={"folder_paths": [str(folder)], "timeout_seconds": 120, "sandbox_mode": "none"},
        )

        assert response.status_code == 200
        archive = ZipFile(BytesIO(response.content))
        names = set(archive.namelist())
        assert "processing_report.json" in names
        assert "teste_kim/resultado.csv" in names


def test_processamento_automatizado_por_caminho_grava_na_pasta_origem(monkeypatch):
    client = _client()

    with tempfile.TemporaryDirectory(prefix="test_auto_proc_") as tmp_dir:
        base = Path(tmp_dir)
        allowed_root = base / "allow"
        folder = allowed_root / "teste_kim"
        folder.mkdir(parents=True)
        (folder / "input.xlsx").write_bytes(b"input")
        (folder / "processamento.py").write_text(
            "from pathlib import Path\nPath('resultado_origem.csv').write_text('ok\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("AUTOMATED_PROCESSING_SERVER_ALLOWLIST", str(allowed_root))

        response = client.post(
            "/processamento-automatizado/process-server-paths",
            json={
                "folder_paths": [str(folder)],
                "timeout_seconds": 120,
                "sandbox_mode": "none",
                "write_to_source": True,
            },
        )

        assert response.status_code == 200
        assert (folder / "resultado_origem.csv").exists()


def test_processamento_automatizado_por_caminho_bloqueia_fora_da_allowlist(monkeypatch):
    client = _client()

    with tempfile.TemporaryDirectory(prefix="test_auto_proc_") as tmp_dir:
        base = Path(tmp_dir)
        allowed_root = base / "allow"
        outside_root = base / "outside"
        folder = outside_root / "pasta_externa"
        folder.mkdir(parents=True)
        (folder / "input.xlsx").write_bytes(b"input")
        (folder / "processamento.py").write_text(
            "from pathlib import Path\nPath('resultado.csv').write_text('ok\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("AUTOMATED_PROCESSING_SERVER_ALLOWLIST", str(allowed_root))

        response = client.post(
            "/processamento-automatizado/process-server-paths",
            json={"folder_paths": [str(folder)], "timeout_seconds": 120, "sandbox_mode": "none"},
        )

        assert response.status_code == 400
        assert "allowlist" in str(response.json()["detail"]).lower()


def test_processamento_automatizado_repasse_de_sandbox_mode(monkeypatch):
    client = _client()

    with tempfile.TemporaryDirectory(prefix="test_auto_proc_") as tmp_dir:
        work_dir = Path(tmp_dir) / "work"
        work_dir.mkdir(parents=True)
        archive_path = work_dir / "resultado.zip"
        archive_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

        captured: dict[str, object] = {}

        def fake_run(artifacts, timeout_seconds=300, sandbox_mode="none"):
            captured["sandbox_mode"] = sandbox_mode
            captured["timeout_seconds"] = timeout_seconds
            return AutomatedProcessingResult(
                archive_path=archive_path,
                working_dir=work_dir,
                folders=[],
                folder_statuses=[],
            )

        monkeypatch.setattr(processamento_automatizado, "run_folder_processing_batch", fake_run)

        files = [
            ("files", ("folder/input.xlsx", b"conteudo", "application/octet-stream")),
            ("files", ("folder/processamento.py", b"print('ok')", "text/x-python")),
        ]

        response = client.post(
            "/processamento-automatizado/process?sandbox_mode=docker&timeout_seconds=90",
            files=files,
        )

        assert response.status_code == 200
        assert captured["sandbox_mode"] == "docker"
        assert captured["timeout_seconds"] == 90


def test_processamento_automatizado_rejeita_sandbox_mode_invalido():
    client = _client()

    files = [
        ("files", ("folder/input.xlsx", b"conteudo", "application/octet-stream")),
        ("files", ("folder/processamento.py", b"print('ok')", "text/x-python")),
    ]

    response = client.post(
        "/processamento-automatizado/process?sandbox_mode=invalid",
        files=files,
    )

    assert response.status_code == 400
    assert "sandbox_mode" in str(response.json()["detail"]).lower()


def test_processamento_automatizado_sandbox_health_none():
    client = _client()

    response = client.get(
        "/processamento-automatizado/sandbox-health",
        params={"sandbox_mode": "none", "pull_image": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["sandbox_mode"] == "none"


def test_processamento_automatizado_sandbox_health_docker_mock(monkeypatch):
    client = _client()

    def fake_health(**kwargs):
        return SandboxHealthResult(
            ready=True,
            sandbox_mode="docker",
            docker_available=True,
            image="python:3.11-slim",
            image_pull_ok=True,
            docker_version="26.1.0",
            message="Sandbox Docker validado com sucesso.",
        )

    monkeypatch.setattr(processamento_automatizado, "validate_sandbox_health", fake_health)

    response = client.get(
        "/processamento-automatizado/sandbox-health",
        params={"sandbox_mode": "docker", "pull_image": True, "timeout_seconds": 60},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["sandbox_mode"] == "docker"
    assert body["image_pull_ok"] is True
