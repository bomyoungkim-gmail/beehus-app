import io
import sys
import types
import uuid
from pathlib import Path

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

if "holidays" not in sys.modules:
    holidays_stub = types.ModuleType("holidays")

    class _EmptyHolidays(dict):
        pass

    def _country_holidays(*args, **kwargs):
        return _EmptyHolidays()

    holidays_stub.country_holidays = _country_holidays
    sys.modules["holidays"] = holidays_stub


from app.console.routers import conferencia_ativo


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(conferencia_ativo.router)
    return TestClient(app)


def test_process_csv_rejects_non_csv():
    client = _client()
    files = {"file": ("entrada.txt", io.BytesIO(b"abc"), "text/plain")}
    response = client.post("/conferencia-ativo/process-csv", files=files)
    assert response.status_code == 400
    assert response.json()["detail"] == "Only CSV files are supported"


def test_process_csv_returns_generated_csv(monkeypatch):
    tmp_path = Path("artifacts") / f"test_conferencia_{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(conferencia_ativo, "_artifacts_dir", lambda: tmp_path)

    def _fake_process(input_path: Path, output_path: Path, **kwargs):
        assert input_path.exists()
        output_path.write_text(
            "Ativo Original,Codigo Ativo,Taxa,Data Vencimento\n"
            "CRA FLU CRA021002N3,CRA021002N3,IPCA + 6,3893%,16/02/2032\n",
            encoding="utf-8-sig",
        )
        return output_path

    monkeypatch.setattr(conferencia_ativo, "processar_csv_arquivo", _fake_process)

    client = _client()
    csv_content = (
        "Ativo Original\n"
        "CRA FLU CRA021002N3 - TESTE\n"
    ).encode("utf-8")
    files = {"file": ("entrada.csv", io.BytesIO(csv_content), "text/csv")}
    response = client.post(
        "/conferencia-ativo/process-csv?use_selenium=false&headless=true&save_every=10",
        files=files,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert "Ativo Original" in response.text
