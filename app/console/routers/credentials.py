"""
Credentials Router - API endpoints for managing secure credentials.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from core.models.mongo_models import Credential
from core.security import encrypt_value, decrypt_value

router = APIRouter(prefix="/credentials", tags=["credentials"])


# Schemas
class CredentialCreate(BaseModel):
    workspace_id: str
    label: str
    username: str
    password: str
    metadata: dict = {}
    carteira: Optional[str] = None
    enable_processing: bool = False


class CredentialUpdate(BaseModel):
    label: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    metadata: Optional[dict] = None
    carteira: Optional[str] = None
    enable_processing: Optional[bool] = None


class CredentialResponse(BaseModel):
    id: str
    workspace_id: str
    label: str
    username: str
    metadata: dict
    carteira: Optional[str] = None
    enable_processing: bool = False
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# Endpoints
@router.post("", response_model=CredentialResponse)
async def create_credential(cred_in: CredentialCreate):
    """Create a new credential with encrypted password."""
    encrypted_password = encrypt_value(cred_in.password)
    
    credential = Credential(
        workspace_id=cred_in.workspace_id,
        label=cred_in.label,
        username=cred_in.username,
        encrypted_password=encrypted_password,
        metadata=cred_in.metadata,
        carteira=cred_in.carteira,
        enable_processing=cred_in.enable_processing,
    )
    await credential.save()
    
    return CredentialResponse(
        id=str(credential.id),
        workspace_id=credential.workspace_id,
        label=credential.label,
        username=credential.username,
        metadata=credential.metadata,
        carteira=credential.carteira,
        enable_processing=credential.enable_processing,
        created_at=credential.created_at.isoformat(),
        updated_at=credential.updated_at.isoformat()
    )


@router.get("", response_model=List[CredentialResponse])
async def list_credentials(workspace_id: Optional[str] = None):
    """List all credentials, optionally filtered by workspace."""
    if workspace_id:
        credentials = await Credential.find(
            Credential.workspace_id == workspace_id
        ).to_list()
    else:
        credentials = await Credential.find_all().to_list()
    
    return [
        CredentialResponse(
            id=str(cred.id),
            workspace_id=cred.workspace_id,
            label=cred.label,
            username=cred.username,
            metadata=cred.metadata,
            carteira=cred.carteira,
            enable_processing=cred.enable_processing,
            created_at=cred.created_at.isoformat(),
            updated_at=cred.updated_at.isoformat()
        )
        for cred in credentials
    ]


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(credential_id: str):
    """Get a specific credential by ID."""
    credential = await Credential.get(credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    
    return CredentialResponse(
        id=str(credential.id),
        workspace_id=credential.workspace_id,
        label=credential.label,
        username=credential.username,
        metadata=credential.metadata,
        carteira=credential.carteira,
        enable_processing=credential.enable_processing,
        created_at=credential.created_at.isoformat(),
        updated_at=credential.updated_at.isoformat()
    )


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(credential_id: str, cred_update: CredentialUpdate):
    """Update an existing credential."""
    from datetime import datetime
    
    credential = await Credential.get(credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    
    # Update fields if provided
    if cred_update.label is not None:
        credential.label = cred_update.label
    if cred_update.username is not None:
        credential.username = cred_update.username
    if cred_update.password is not None:
        credential.encrypted_password = encrypt_value(cred_update.password)
    if cred_update.metadata is not None:
        credential.metadata = cred_update.metadata
    if cred_update.carteira is not None:
        credential.carteira = cred_update.carteira
    if cred_update.enable_processing is not None:
        credential.enable_processing = cred_update.enable_processing
    
    credential.updated_at = datetime.utcnow()
    await credential.save()
    
    return CredentialResponse(
        id=str(credential.id),
        workspace_id=credential.workspace_id,
        label=credential.label,
        username=credential.username,
        metadata=credential.metadata,
        carteira=credential.carteira,
        enable_processing=credential.enable_processing,
        created_at=credential.created_at.isoformat(),
        updated_at=credential.updated_at.isoformat()
    )


@router.delete("/{credential_id}")
async def delete_credential(credential_id: str):
    """Delete a credential."""
    credential = await Credential.get(credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    
    await credential.delete()
    return {"message": f"Credential {credential_id} deleted successfully"}
