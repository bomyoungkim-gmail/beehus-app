"""
MongoDB document models using Beanie ODM.
These models replace the SQLAlchemy models for MongoDB-only architecture.
"""

from beanie import Document, Indexed
from datetime import datetime
from typing import Optional, List
from pydantic import Field
import uuid
from core.utils.date_utils import get_now


def generate_uuid():
    """Generate UUID string for document IDs"""
    return str(uuid.uuid4())


class User(Document):
    id: str = Field(default_factory=generate_uuid)
    email: Indexed(str, unique=True)
    password_hash: str
    full_name: Optional[str] = None
    role: str = "user"  # admin, user
    created_at: datetime = Field(default_factory=get_now)
    
    class Settings:
        name = "users"

class Workspace(Document):
    """Workspace document - top-level organization unit"""
    id: str = Field(default_factory=generate_uuid)
    name: Indexed(str, unique=True)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=get_now)
    
    class Settings:
        name = "workspaces"


class InboxIntegration(Document):
    """Gmail/Inbox integration for OTP capture"""
    id: str = Field(default_factory=generate_uuid)
    workspace_id: Indexed(str)
    provider: str = "gmail"
    status: str = "active"  # active, revoked, error
    email_address: Optional[str] = None
    token_ciphertext: str  # Encrypted refresh token
    scopes: List[str] = []
    created_at: datetime = Field(default_factory=get_now)
    updated_at: datetime = Field(default_factory=get_now)
    
    class Settings:
        name = "inbox_integrations"


class OtpRule(Document):
    """Rules for OTP code extraction from emails"""
    id: str = Field(default_factory=generate_uuid)
    workspace_id: Indexed(str)
    name: str
    provider: str = "gmail"
    gmail_query: str  # e.g. "subject:code newer_than:1d"
    otp_regex: str    # e.g. "(\\d{6})"
    ttl_seconds: int = 300
    timeout_seconds: int = 180
    created_at: datetime = Field(default_factory=get_now)
    
    class Settings:
        name = "otp_rules"


class Credential(Document):
    """Secure credential storage for scraping"""
    id: str = Field(default_factory=generate_uuid)
    workspace_id: Indexed(str)
    label: str
    username: str
    encrypted_password: str
    metadata: dict = {}
    created_at: datetime = Field(default_factory=get_now)
    updated_at: datetime = Field(default_factory=get_now)

    class Settings:
        name = "credentials"


class Job(Document):
    """Scraping job configuration"""
    id: str = Field(default_factory=generate_uuid)
    workspace_id: Indexed(str)
    name: str
    connector: Indexed(str)  # Connector name (e.g., "example", "linkedin")
    credential_id: Optional[str] = None  # Reference to Credential document
    params: dict = {}  # Job-specific parameters
    schedule: Optional[str] = None  # Cron expression for periodic execution
    status: str = "active"  # active, paused, deleted
    created_at: datetime = Field(default_factory=get_now)
    
    class Settings:
        name = "jobs"


class Run(Document):
    """Individual execution of a job"""
    id: str = Field(default_factory=generate_uuid)
    job_id: Indexed(str)
    connector: Optional[str] = None  # Connector name for display
    status: str = "queued"  # queued, running, success, failed
    attempt: int = 1
    celery_task_id: Optional[str] = None  # For task cancellation
    error_summary: Optional[str] = None
    logs: List[str] = []
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=get_now)
    updated_at: Optional[datetime] = Field(default_factory=get_now)
    
    class Settings:
        name = "runs"


class OtpAudit(Document):
    """Audit log for OTP capture attempts"""
    id: str = Field(default_factory=generate_uuid)
    run_id: Indexed(str)
    workspace_id: str
    provider: str = "gmail"
    otp_rule_id: Optional[str] = None
    gmail_message_id: Optional[str] = None
    status: str  # found, timeout, error
    detail: Optional[str] = None
    created_at: datetime = Field(default_factory=get_now)
    
    class Settings:
        name = "otp_audit"

MONGO_MODELS = [
    User, Workspace, Job, Run, InboxIntegration, OtpRule, OtpAudit, Credential
]
