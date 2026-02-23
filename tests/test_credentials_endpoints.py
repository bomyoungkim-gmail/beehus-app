import sys
import types
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient


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


from app.console.routers import credentials


class _CredentialDoc:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.id = "cred-1"
        self.workspace_id = "ws-1"
        self.label = "Main"
        self.username = "user-1"
        self.encrypted_password = "encrypted-old"
        self.metadata = {"agencia": "1234"}
        self.carteira = None
        self.created_at = now
        self.updated_at = now

    async def save(self):
        return None


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(credentials.router)
    return TestClient(app)


def test_update_credential_blank_password_does_not_overwrite(monkeypatch):
    doc = _CredentialDoc()

    async def _get(_id):
        return doc

    monkeypatch.setattr(credentials.Credential, "get", _get, raising=False)
    monkeypatch.setattr(credentials, "encrypt_value", lambda value: f"enc:{value}")

    client = _client()
    res = client.put(
        "/credentials/cred-1",
        json={"password": "", "label": "Updated"},
    )
    assert res.status_code == 200
    assert doc.label == "Updated"
    assert doc.encrypted_password == "encrypted-old"


def test_update_credential_non_empty_password_overwrites(monkeypatch):
    doc = _CredentialDoc()

    async def _get(_id):
        return doc

    monkeypatch.setattr(credentials.Credential, "get", _get, raising=False)
    monkeypatch.setattr(credentials, "encrypt_value", lambda value: f"enc:{value}")

    client = _client()
    res = client.put(
        "/credentials/cred-1",
        json={"password": "new-secret"},
    )
    assert res.status_code == 200
    assert doc.encrypted_password == "enc:new-secret"
