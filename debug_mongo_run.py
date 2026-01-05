import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import uuid

# Run ID reported by user
RUN_ID_STR = "3b5ef2d4-3f08-468c-b912-ab378ac83d45"
# Default dev credentials from docker-compose.yml
MONGO_URI = "mongodb://admin:adminpass@mongo:27017"
DB_NAME = "platform_db"

async def inspect_run():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db["runs"] # Beanie collection name is 'runs'

    print(f"--- Inspecting Run: {RUN_ID_STR} ---")

    # 1. Try finding by String ID
    doc_str = await collection.find_one({"_id": RUN_ID_STR})
    print(f"Find by String ID: {'FOUND' if doc_str else 'NOT FOUND'}")
    if doc_str:
        print(f"  Type of _id: {type(doc_str['_id'])}")
        print(f"  Status: {doc_str.get('status')}")

    # 2. Try finding by UUID object
    try:
        run_uuid = uuid.UUID(RUN_ID_STR)
        doc_uuid = await collection.find_one({"_id": run_uuid})
        print(f"Find by UUID Object: {'FOUND' if doc_uuid else 'NOT FOUND'}")
        if doc_uuid:
            print(f"  Type of _id: {type(doc_uuid['_id'])}")
            print(f"  Status: {doc_uuid.get('status')}")
    except Exception as e:
        print(f"UUID conversion error: {e}")

    client.close()

if __name__ == "__main__":
    asyncio.run(inspect_run())
