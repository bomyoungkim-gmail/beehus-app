"""
OTP Router - API endpoints for Inbox Integrations and OTP Rules.
"""

import os
from fastapi import APIRouter, HTTPException
from cryptography.fernet import Fernet
from typing import List, Optional

from core.models.mongo_models import InboxIntegration, OtpRule
from core.schemas.otp import (
    InboxIntegrationCreate, InboxIntegrationResponse,
    OtpRuleCreate, OtpRuleResponse,
)

router = APIRouter(tags=["otp"])


# ---------------------------------------------------------------------------
# Token helpers (Inbox Integration tokens are encrypted with a separate key)
# ---------------------------------------------------------------------------

def _token_fernet() -> Fernet:
    raw_key = os.getenv("TOKEN_ENC_KEY", "").strip()
    if not raw_key:
        raise RuntimeError(
            "TOKEN_ENC_KEY is not configured. Set a valid Fernet key in environment."
        )
    try:
        return Fernet(raw_key.encode())
    except Exception as exc:
        raise RuntimeError(
            "Invalid TOKEN_ENC_KEY. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


def _encrypt_token(token: str) -> str:
    return _token_fernet().encrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# Inbox Integrations
# ---------------------------------------------------------------------------

@router.post("/inbox_integrations", response_model=InboxIntegrationResponse)
async def create_inbox_integration(integration_in: InboxIntegrationCreate):
    """Create a new inbox integration (e.g., Gmail)."""
    integration = InboxIntegration(
        workspace_id=integration_in.workspace_id,
        provider="gmail",
        email_address=integration_in.email_address,
        token_ciphertext=_encrypt_token(integration_in.refresh_token),
        scopes=integration_in.scopes or [],
    )
    await integration.save()
    return integration


@router.get("/inbox_integrations", response_model=List[InboxIntegrationResponse])
async def list_inbox_integrations(workspace_id: Optional[str] = None):
    """List inbox integrations, optionally filtered by workspace."""
    if workspace_id:
        return await InboxIntegration.find(
            InboxIntegration.workspace_id == workspace_id
        ).to_list()
    return await InboxIntegration.find_all().to_list()


# ---------------------------------------------------------------------------
# OTP Rules
# ---------------------------------------------------------------------------

@router.post("/otp_rules", response_model=OtpRuleResponse)
async def create_otp_rule(rule_in: OtpRuleCreate):
    """Create a new OTP extraction rule."""
    rule = OtpRule(**rule_in.model_dump())
    await rule.save()
    return rule


@router.get("/otp_rules", response_model=List[OtpRuleResponse])
async def list_otp_rules(workspace_id: Optional[str] = None):
    """List OTP rules, optionally filtered by workspace."""
    if workspace_id:
        return await OtpRule.find(OtpRule.workspace_id == workspace_id).to_list()
    return await OtpRule.find_all().to_list()
