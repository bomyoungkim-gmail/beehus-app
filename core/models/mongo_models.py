"""
MongoDB document models using Beanie ODM.
These models replace the SQLAlchemy models for MongoDB-only architecture.
"""

from beanie import Document, Indexed
from datetime import datetime
from typing import Optional, List
from pydantic import Field, BaseModel
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
    is_active: bool = True
    invited_by: Optional[str] = None
    invitation_token: Optional[str] = None
    invitation_expires_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    password_reset_token: Optional[str] = None
    password_reset_expires_at: Optional[datetime] = None
    
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
    carteira: Optional[str] = None
    enable_processing: bool = False
    created_at: datetime = Field(default_factory=get_now)
    updated_at: datetime = Field(default_factory=get_now)

    class Settings:
        name = "credentials"


class FileProcessor(Document):
    """File processor associated with a credential."""
    id: str = Field(default_factory=generate_uuid)
    credential_id: Indexed(str)
    name: str
    version: int = 1
    processor_type: str = "python_script"
    script_content: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=get_now)
    updated_at: datetime = Field(default_factory=get_now)

    class Settings:
        name = "file_processors"


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
    
    # Export options
    export_holdings: bool = True  # Export portfolio report
    export_history: bool = False   # Export transaction statement
    
    # Date configuration mode (mutually exclusive)
    date_mode: str = "lag"  # "lag" or "specific"
    
    # Lag-based configuration (when date_mode = "lag")
    holdings_lag_days: int = 1  # D-1 by default
    history_lag_days: int = 2    # D-2 by default
    
    # Specific date configuration (when date_mode = "specific")
    holdings_date: Optional[str] = None  # Format: YYYY-MM-DD
    history_date: Optional[str] = None    # Format: YYYY-MM-DD
    last_selected_filename: Optional[str] = None
    last_selected_sheet: Optional[str] = None
    selection_updated_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=get_now)
    
    class Settings:
        name = "jobs"


class RunFile(BaseModel):
    """Metadata for a downloadable run file."""
    file_type: str
    filename: str
    path: str
    size_bytes: Optional[int] = None
    status: str = "ready"
    is_excel: Optional[bool] = None
    sheet_options: List[str] = Field(default_factory=list)
    is_latest: bool = False


class Run(Document):
    """Individual execution of a job"""
    id: str = Field(default_factory=generate_uuid)
    job_id: Indexed(str)
    job_name: Optional[str] = None
    connector: Optional[str] = None  # Connector name for display
    status: str = "queued"  # queued, running, success, failed
    attempt: int = 1
    celery_task_id: Optional[str] = None  # For task cancellation
    error_summary: Optional[str] = None
    logs: List[str] = []
    vnc_url: Optional[str] = None
    report_date: Optional[str] = None  # Position Date (DD/MM/YYYY)
    history_date: Optional[str] = None  # History Date (DD/MM/YYYY)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=get_now)
    updated_at: Optional[datetime] = Field(default_factory=get_now)
    files: List[RunFile] = Field(default_factory=list)
    processing_status: str = "not_required"
    selected_filename: Optional[str] = None
    selected_sheet: Optional[str] = None
    processing_error: Optional[str] = None
    
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
    User, Workspace, Job, Run, InboxIntegration, OtpRule, OtpAudit, Credential, FileProcessor
]
