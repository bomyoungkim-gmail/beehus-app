from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.console.routers.auth import get_current_user
from core.auth import create_access_token, create_refresh_token, verify_password, get_password_hash
from core.models.mongo_models import User
from core.services import user_service


router = APIRouter(prefix="/users", tags=["users"])


class InviteRequest(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: str = "user"


class InviteResponse(BaseModel):
    invitation_token: str
    invitation_link: str
    expires_at: datetime
    email_sent: bool


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str
    full_name: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: UserOut


class RequestPasswordReset(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None


class UpdateMeRequest(BaseModel):
    full_name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


@router.post("/invite", response_model=InviteResponse)
async def invite_user(
    payload: InviteRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return await user_service.create_invitation(
            current_user,
            email=payload.email,
            full_name=payload.full_name,
            role=payload.role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[UserOut])
async def list_users(current_user: User = Depends(get_current_user)):
    try:
        users = await user_service.list_users(current_user)
        return users
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return await user_service.update_user(current_user, user_id, payload.dict())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        await user_service.deactivate_user(current_user, user_id)
        return {"message": "User deactivated"}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/activate")
async def activate_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        await user_service.activate_user(current_user, user_id)
        return {"message": "User activated"}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/accept-invitation", response_model=TokenResponse)
async def accept_invitation(payload: AcceptInvitationRequest):
    try:
        user = await user_service.accept_invitation(
            token=payload.token,
            password=payload.password,
            full_name=payload.full_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    access_token = create_access_token({"sub": user.email, "user_id": user.id})
    refresh_token = create_refresh_token({"sub": user.email, "user_id": user.id})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }


@router.post("/request-password-reset")
async def request_password_reset(payload: RequestPasswordReset):
    await user_service.request_password_reset(payload.email)
    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    try:
        await user_service.reset_password(payload.token, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Password updated successfully"}


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name

    if payload.new_password or payload.current_password:
        if not payload.current_password or not payload.new_password:
            raise HTTPException(status_code=400, detail="Current and new passwords required")
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        current_user.password_hash = get_password_hash(payload.new_password)

    await current_user.save()
    return current_user
