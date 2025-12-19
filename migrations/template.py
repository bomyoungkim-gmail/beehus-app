"""
Migration template

Copy this file to create a new migration:
cp migrations/template.py migrations/00X_description.py
"""

async def up(db):
    """
    Apply migration changes
    
    Args:
        db: Motor AsyncIOMotorDatabase instance
    
    Example:
        await db.collection_name.create_index("field_name")
        await db.collection_name.update_many({}, {"$set": {"new_field": "value"}})
    """
    pass


async def down(db):
    """
    Rollback migration changes
    
    Args:
        db: Motor AsyncIOMotorDatabase instance
    
    Example:
        await db.collection_name.drop_index("field_name_1")
        await db.collection_name.update_many({}, {"$unset": {"new_field": ""}})
    """
    pass
