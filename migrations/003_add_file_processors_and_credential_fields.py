"""
Migration: Add file processors collection and credential processing fields.
Date: 2026-02-12
"""


async def up(db):
    credentials = db.credentials
    file_processors = db.file_processors

    await credentials.update_many(
        {"enable_processing": {"$exists": False}},
        {"$set": {"enable_processing": False}},
    )
    await credentials.update_many(
        {"carteira": {"$exists": False}},
        {"$set": {"carteira": None}},
    )

    await file_processors.create_index("credential_id")
    await file_processors.create_index([("credential_id", 1), ("is_active", 1)])


async def down(db):
    credentials = db.credentials
    file_processors = db.file_processors

    await credentials.update_many(
        {},
        {"$unset": {"enable_processing": "", "carteira": ""}},
    )

    await file_processors.drop_indexes()
