import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Lightweight stub so router import does not require full Beanie installation.
if "beanie" not in sys.modules:
    beanie_stub = types.ModuleType("beanie")

    class _Document:
        pass

    def _indexed(field_type, unique=False):
        return field_type

    beanie_stub.Document = _Document
    beanie_stub.Indexed = _indexed
    sys.modules["beanie"] = beanie_stub

if "holidays" not in sys.modules:
    holidays_stub = types.ModuleType("holidays")

    class _EmptyHolidays(dict):
        pass

    def _country_holidays(*args, **kwargs):
        return _EmptyHolidays()

    holidays_stub.country_holidays = _country_holidays
    sys.modules["holidays"] = holidays_stub

from app.console.routers import downloads
import pytest


class DummyRun:
    def __init__(self, run_id: str, job_id: str, files: list[dict], selected_filename: str | None = None):
        self.id = run_id
        self.job_id = job_id
        self.files = files
        self.selected_filename = selected_filename
        self.processing_error = None
        self.last_update = None

    async def update(self, payload):
        self.last_update = payload


class DummyJob:
    def __init__(
        self,
        credential_id: str,
        last_selected_sheet: str | None = None,
        last_selected_filename: str | None = None,
    ):
        self.credential_id = credential_id
        self.last_selected_sheet = last_selected_sheet
        self.last_selected_filename = last_selected_filename
        self.last_update = None

    async def update(self, payload):
        self.last_update = payload


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(downloads.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _always_acquire_lock(monkeypatch):
    async def _ok(*args, **kwargs):
        return True
    monkeypatch.setattr(downloads.FileProcessorService, "_acquire_processing_lock", _ok, raising=False)


def test_select_file_non_excel_saves_selection_only(monkeypatch):
    run = DummyRun(
        run_id="run-1",
        job_id="job-1",
        files=[{"file_type": "original", "filename": "positions.csv", "path": "run-1/original/positions.csv"}],
    )
    job = DummyJob(credential_id="cred-1")

    async def fake_run_get(run_id):
        assert run_id == "run-1"
        return run

    async def fake_job_get(job_id):
        assert job_id == "job-1"
        return job

    monkeypatch.setattr(downloads.Run, "get", fake_run_get, raising=False)
    monkeypatch.setattr(downloads.Job, "get", fake_job_get, raising=False)

    client = _client()
    res = client.post("/downloads/run-1/processing/select-file", json={"filename": "positions.csv"})
    assert res.status_code == 200
    assert res.json()["status"] == "pending_reprocess"
    assert run.last_update["$set"]["processing_status"] == "pending_reprocess"
    assert run.last_update["$set"]["selected_filename"] == "positions.csv"


def test_select_file_excel_goes_pending_sheet_when_multiple_sheets(monkeypatch):
    run = DummyRun(
        run_id="run-2",
        job_id="job-2",
        files=[{"file_type": "original", "filename": "positions.xlsx", "path": "run-2/original/positions.xlsx"}],
    )
    job = DummyJob(credential_id="cred-2", last_selected_sheet=None)

    async def fake_run_get(run_id):
        return run

    async def fake_job_get(job_id):
        return job

    async def fake_get_excel_options(run_id, filename=None):
        return ["SheetA", "SheetB"]

    async def should_not_process(*args, **kwargs):
        raise AssertionError("Processing should not start before sheet selection")

    monkeypatch.setattr(downloads.Run, "get", fake_run_get, raising=False)
    monkeypatch.setattr(downloads.Job, "get", fake_job_get, raising=False)
    monkeypatch.setattr(downloads, "get_excel_options", fake_get_excel_options)
    monkeypatch.setattr(downloads.FileProcessorService, "process_with_user_selection", should_not_process)

    client = _client()
    res = client.post("/downloads/run-2/processing/select-file", json={"filename": "positions.xlsx"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "pending_sheet_selection"
    assert body["sheet_options"] == ["SheetA", "SheetB"]
    assert run.last_update is not None
    assert run.last_update["$set"]["processing_status"] == "pending_sheet_selection"
    assert run.last_update["$set"]["selected_filename"] == "positions.xlsx"


def test_select_sheet_endpoint_saves_selection_only(monkeypatch):
    run = DummyRun(
        run_id="run-3",
        job_id="job-3",
        files=[{"file_type": "original", "filename": "positions.xlsx", "path": "run-3/original/positions.xlsx"}],
    )

    job = DummyJob(credential_id="cred-3")

    async def fake_run_get(run_id):
        return run

    async def fake_job_get(job_id):
        return job

    monkeypatch.setattr(downloads.Run, "get", fake_run_get, raising=False)
    monkeypatch.setattr(downloads.Job, "get", fake_job_get, raising=False)

    client = _client()
    res = client.post(
        "/downloads/run-3/processing/select-sheet",
        json={"filename": "positions.xlsx", "selected_sheet": "SheetA"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "pending_reprocess"
    assert run.last_update["$set"]["processing_status"] == "pending_reprocess"
    assert run.last_update["$set"]["selected_sheet"] == "SheetA"


def test_reprocess_pending_file_selection_when_ambiguous(monkeypatch):
    run = DummyRun(
        run_id="run-4",
        job_id="job-4",
        files=[
            {"file_type": "original", "filename": "a.xlsx", "path": "run-4/original/a.xlsx"},
            {"file_type": "original", "filename": "b.xlsx", "path": "run-4/original/b.xlsx"},
        ],
        selected_filename=None,
    )
    job = DummyJob(credential_id="cred-4", last_selected_sheet=None)

    async def fake_run_get(run_id):
        return run

    async def fake_job_get(job_id):
        return job

    monkeypatch.setattr(downloads.Run, "get", fake_run_get, raising=False)
    monkeypatch.setattr(downloads.Job, "get", fake_job_get, raising=False)

    client = _client()
    res = client.post("/downloads/run-4/processing/process", json={})
    assert res.status_code == 200
    assert res.json()["status"] == "pending_file_selection"
    assert run.last_update is not None
    assert run.last_update["$set"]["processing_status"] == "pending_file_selection"


def test_integration_pending_to_select_sheet_to_processed(monkeypatch):
    run = DummyRun(
        run_id="run-5",
        job_id="job-5",
        files=[
            {"file_type": "original", "filename": "positions.xlsx", "path": "run-5/original/positions.xlsx"},
        ],
        selected_filename=None,
    )
    job = DummyJob(credential_id="cred-5", last_selected_sheet=None)

    async def fake_run_get(run_id):
        return run

    async def fake_job_get(job_id):
        return job

    async def fake_get_excel_options(run_id, filename=None):
        return ["SheetA", "SheetB"]

    monkeypatch.setattr(downloads.Run, "get", fake_run_get, raising=False)
    monkeypatch.setattr(downloads.Job, "get", fake_job_get, raising=False)
    monkeypatch.setattr(downloads, "get_excel_options", fake_get_excel_options)

    client = _client()
    options = client.get("/downloads/run-5/processing/options")
    assert options.status_code == 200
    assert options.json()[0]["filename"] == "positions.xlsx"

    select_file = client.post("/downloads/run-5/processing/select-file", json={"filename": "positions.xlsx"})
    assert select_file.status_code == 200
    assert select_file.json()["status"] == "pending_sheet_selection"
    assert run.last_update is not None
    assert run.last_update["$set"]["processing_status"] == "pending_sheet_selection"

    select_sheet = client.post(
        "/downloads/run-5/processing/select-sheet",
        json={"filename": "positions.xlsx", "selected_sheet": "SheetA"},
    )
    assert select_sheet.status_code == 200
    assert select_sheet.json()["status"] == "pending_reprocess"


def test_reprocess_from_processed_uses_script_snapshot(monkeypatch):
    run = DummyRun(
        run_id="run-6",
        job_id="job-6",
        files=[
            {"file_type": "original", "filename": "positions.xlsx", "path": "run-6/original/positions.xlsx"},
            {
                "file_type": "processed",
                "filename": "positions_processado-01-01-2026--10-00-00.csv",
                "path": "run-6/processed/positions_processado-01-01-2026--10-00-00.csv",
                "processor_script_snapshot": "return df_input",
                "processor_name": "Proc",
                "processor_version": 3,
            },
        ],
        selected_filename="positions.xlsx",
    )
    job = DummyJob(credential_id="cred-6", last_selected_sheet="Plan1")
    captured = {}

    async def fake_run_get(run_id):
        return run

    async def fake_job_get(job_id):
        return job

    async def fake_process_with_selection(
        run_id,
        filename,
        selected_sheet=None,
        script_override=None,
        processor_snapshot_override=None,
    ):
        captured["run_id"] = run_id
        captured["filename"] = filename
        captured["selected_sheet"] = selected_sheet
        captured["script_override"] = script_override
        captured["processor_snapshot_override"] = processor_snapshot_override
        return "processed"

    monkeypatch.setattr(downloads.Run, "get", fake_run_get, raising=False)
    monkeypatch.setattr(downloads.Job, "get", fake_job_get, raising=False)
    monkeypatch.setattr(downloads.FileProcessorService, "process_with_user_selection", fake_process_with_selection)

    client = _client()
    res = client.post(
        "/downloads/run-6/processing/reprocess-from-processed",
        json={"processed_filename": "positions_processado-01-01-2026--10-00-00.csv"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert captured["script_override"] == "return df_input"
    assert captured["filename"] == "positions.xlsx"
    assert captured["processor_snapshot_override"]["processor_source"] == "snapshot"
