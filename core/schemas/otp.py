from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class OtpRequestMessage(BaseModel):
    run_id: str
    job_id: str
    workspace_id: str
    otp_rule_id: Optional[str] = None # If connector knows specific rule, else generic
    attempt: int
    requested_at: datetime = Field(default_factory=datetime.utcnow)

class WorkspaceCreate(BaseModel):
    name: str

class WorkspaceResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    class Config:
        from_attributes = True

class InboxIntegrationCreate(BaseModel):
    client_id: str
    client_secret: str
    refresh_token: str
    email_address: Optional[str] = None

class InboxIntegrationResponse(BaseModel):
    id: str
    provider: str
    email_address: Optional[str]
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class OtpRuleCreate(BaseModel):
    name: str
    provider: str = "gmail"
    gmail_query: str
    otp_regex: str
    ttl_seconds: int = 300
    timeout_seconds: int = 180

class OtpRuleResponse(OtpRuleCreate):
    id: str
    workspace_id: str
    created_at: datetime
    class Config:
        from_attributes = True
