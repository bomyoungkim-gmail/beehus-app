import sys
import types
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient


# Lightweight stubs so router imports do not require full runtime deps.
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


from app.console.routers import dashboard


class _CountQuery:
    def __init__(self, value: int):
        self.value = value

    async def count(self):
        return self.value


class _AggCursor:
    def __init__(self, result):
        self.result = result

    async def to_list(self, length=1):
        return self.result


class _Collection:
    def __init__(self, result):
        self.result = result

    def aggregate(self, pipeline):
        return _AggCursor(self.result)


class _RunQuery:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self):
        return self.rows


class _JobListQuery:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self):
        return self.rows


class _RunRow:
    def __init__(self, run_id: str, job_id: str, connector: str | None, job_name: str | None):
        self.id = run_id
        self.job_id = job_id
        self.connector = connector
        self.job_name = job_name
        self.execution_node = "worker-01"
        self.status = "success"
        self.processing_status = "not_required"
        self.selected_filename = None
        self.selected_sheet = None
        self.processing_error = None
        self.report_date = None
        self.history_date = None
        self.created_at = datetime.now(timezone.utc)


class _JobRow:
    def __init__(self, job_id: str, name: str, connector: str):
        self.id = job_id
        self.name = name
        self.connector = connector


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(dashboard.router)
    return TestClient(app)


def test_dashboard_stats_returns_expected_shape(monkeypatch):
    facet = [
        {
            "by_status": [
                {"_id": "success", "count": 10},
                {"_id": "failed", "count": 2},
                {"_id": "running", "count": 1},
                {"_id": "queued", "count": 3},
            ],
            "recent_success": [{"n": 4}],
            "previous_success": [{"n": 2}],
        }
    ]

    monkeypatch.setattr(dashboard.Run, "get_motor_collection", lambda: _Collection(facet), raising=False)
    monkeypatch.setattr(dashboard.Run, "created_at", 1, raising=False)
    monkeypatch.setattr(dashboard.Job, "find", lambda *args, **kwargs: _CountQuery(5), raising=False)

    client = _client()
    res = client.get("/dashboard/stats")
    assert res.status_code == 200
    body = res.json()

    assert body["successful_runs"] == 10
    assert body["failed_runs"] == 2
    assert body["running_runs"] == 1
    assert body["queued_runs"] == 3
    assert body["active_workers"] == 4
    assert body["active_jobs"] == 5
    assert body["total_runs"] == 16


def test_dashboard_recent_runs_fills_missing_job_data(monkeypatch):
    rows = [_RunRow("run-1", "job-1", connector=None, job_name=None)]

    monkeypatch.setattr(dashboard.Run, "find", lambda *args, **kwargs: _RunQuery(rows), raising=False)
    monkeypatch.setattr(dashboard.Run, "created_at", 1, raising=False)

    def _job_find(*args, **kwargs):
        if args and isinstance(args[0], dict):
            return _JobListQuery([_JobRow("job-1", "Job A", "btg_mfo")])
        return _CountQuery(0)

    monkeypatch.setattr(dashboard.Job, "find", _job_find, raising=False)

    client = _client()
    res = client.get("/dashboard/recent-runs?limit=1")
    assert res.status_code == 200
    body = res.json()

    assert len(body) == 1
    assert body[0]["run_id"] == "run-1"
    assert body[0]["job_name"] == "Job A"
    assert body[0]["connector"] == "btg_mfo"
    assert body[0]["node"] == "worker-01"
    assert body[0]["status"] == "success"
