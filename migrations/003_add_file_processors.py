"""
Migration: Add file processors and credential processing fields
Date: 2026-02-12
"""


async def up(db):
    await db.credentials.update_many(
        {"carteira": {"$exists": False}},
        {"$set": {"carteira": None}},
    )
    await db.credentials.update_many(
        {"enable_processing": {"$exists": False}},
        {"$set": {"enable_processing": False}},
    )

    await db.file_processors.create_index("credential_id")
    await db.file_processors.create_index([("credential_id", 1), ("is_active", 1)])


async def down(db):
    await db.credentials.update_many(
        {},
        {"$unset": {"carteira": "", "enable_processing": ""}},
    )

    await db.file_processors.drop_indexes()
