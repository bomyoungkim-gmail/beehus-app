import sys
import types
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient


# Lightweight stubs so router import does not require full runtime deps.
if "beanie" not in sys.modules:
    beanie_stub = types.ModuleType("beanie")

    class _Document:
        pass

    def _indexed(field_type, unique=False):
        return field_type

    beanie_stub.Document = _Document
    beanie_stub.Indexed = _indexed
    sys.modules["beanie"] = beanie_stub

if "django_config" not in sys.modules:
    django_config_stub = types.ModuleType("django_config")

    class _CeleryControl:
        def revoke(self, *args, **kwargs):
            return None

    class _CeleryApp:
        control = _CeleryControl()

    django_config_stub.celery_app = _CeleryApp()
    sys.modules["django_config"] = django_config_stub


from app.console.routers import runs


class _RunRow:
    def __init__(self, run_id: str):
        self.id = run_id
        self.job_id = "job-1"
        self.connector = "btg_mfo"
        self.execution_node = "worker-02"
        self.status = "success"
        self.report_date = None
        self.started_at = datetime.now(timezone.utc)
        self.finished_at = datetime.now(timezone.utc)
        self.created_at = datetime.now(timezone.utc)
        self.error_summary = None
        self.vnc_url = None
        self.logs = []
        self.processing_logs = []
        self.processing_status = "not_required"
        self.selected_filename = None
        self.selected_sheet = None
        self.processing_error = None


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(runs.router)
    return TestClient(app)


def test_get_run_returns_execution_node(monkeypatch):
    async def _get(run_id):
        assert run_id == "run-1"
        return _RunRow("run-1")

    monkeypatch.setattr(runs.Run, "get", _get, raising=False)

    client = _client()
    response = client.get("/runs/run-1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "run-1"
    assert body["execution_node"] == "worker-02"
    assert body["status"] == "success"
