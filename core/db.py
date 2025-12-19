"""
Database initialization for Beanie (MongoDB ODM).
Replaces SQLAlchemy setup.
"""

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from core.config import settings
from core.models.mongo_models import (
    Workspace, Job, Run, InboxIntegration, OtpRule, OtpAudit, User,
    MONGO_MODELS
)

client: AsyncIOMotorClient = None


async def init_db():
    """Initialize Beanie with MongoDB connection"""
    global client
    client = AsyncIOMotorClient(settings.MONGO_URI)
    
    await init_beanie(
        database=client[settings.MONGO_DB_NAME],
        document_models=MONGO_MODELS
    )


async def close_db():
    """Close MongoDB connection"""
    if client:
        client.close()


async def get_db():
    """
    Dependency for FastAPI routes (compatibility with SQLAlchemy pattern).
    With Beanie, we don't need to yield sessions - models are self-contained.
    This is kept for API compatibility but can be removed in favor of direct model usage.
    """
    # No-op for Beanie - models handle their own connection
    yield None
