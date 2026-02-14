"""
File processors API router.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from app.console.schemas import ProcessorCreate, ProcessorResponse, ProcessorUpdate
from core.models.mongo_models import Credential, FileProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/processors", tags=["processors"])


@router.post("/", response_model=dict)
async def create_processor(data: ProcessorCreate):
    """Create a new processor for a credential."""
    credential = await Credential.get(data.credential_id)
    if not credential:
        raise HTTPException(404, "Credential not found")

    await FileProcessor.find(
        FileProcessor.credential_id == data.credential_id
    ).update({"$set": {"is_active": False}})

    processor = FileProcessor(
        credential_id=data.credential_id,
        name=data.name,
        script_content=data.script_content,
        version=1,
        is_active=True,
    )
    await processor.save()

    logger.info("Created processor %s for credential %s", processor.id, data.credential_id)

    return {"id": processor.id, "message": "Processor created", "version": 1}


@router.get("/credential/{credential_id}", response_model=List[ProcessorResponse])
async def list_processors(credential_id: str):
    """List processors for a credential."""
    processors = await FileProcessor.find(
        FileProcessor.credential_id == credential_id
    ).sort("-created_at").to_list()

    return [
        ProcessorResponse(
            id=processor.id,
            credential_id=processor.credential_id,
            name=processor.name,
            version=processor.version,
            processor_type=processor.processor_type,
            is_active=processor.is_active,
            created_at=processor.created_at.isoformat(),
            updated_at=processor.updated_at.isoformat(),
            script_preview=(
                processor.script_content[:200] + "..."
                if len(processor.script_content) > 200
                else processor.script_content
            ),
        )
        for processor in processors
    ]


@router.get("/{processor_id}")
async def get_processor(processor_id: str):
    """Get a processor by ID."""
    processor = await FileProcessor.get(processor_id)
    if not processor:
        raise HTTPException(404, "Processor not found")

    return {
        "id": processor.id,
        "credential_id": processor.credential_id,
        "name": processor.name,
        "version": processor.version,
        "processor_type": processor.processor_type,
        "script_content": processor.script_content,
        "is_active": processor.is_active,
        "created_at": processor.created_at.isoformat(),
        "updated_at": processor.updated_at.isoformat(),
    }


@router.put("/{processor_id}", response_model=dict)
async def update_processor(processor_id: str, data: ProcessorUpdate):
    """Update a processor by creating a new version."""
    old_processor = await FileProcessor.get(processor_id)
    if not old_processor:
        raise HTTPException(404, "Processor not found")

    await old_processor.update({"$set": {"is_active": False}})

    new_processor = FileProcessor(
        credential_id=old_processor.credential_id,
        name=data.name or old_processor.name,
        script_content=data.script_content or old_processor.script_content,
        version=old_processor.version + 1,
        is_active=data.is_active if data.is_active is not None else True,
    )
    await new_processor.save()

    logger.info(
        "Updated processor %s -> %s (v%s)",
        processor_id,
        new_processor.id,
        new_processor.version,
    )

    return {"id": new_processor.id, "version": new_processor.version, "message": "Processor updated"}


@router.delete("/{processor_id}")
async def delete_processor(processor_id: str):
    """Deactivate a processor."""
    processor = await FileProcessor.get(processor_id)
    if not processor:
        raise HTTPException(404, "Processor not found")

    await processor.update({"$set": {"is_active": False}})

    logger.info("Deactivated processor %s", processor_id)

    return {"message": "Processor deactivated"}
