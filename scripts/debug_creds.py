import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys

# Default dev credentials
MONGO_URI = "mongodb://admin:adminpass@mongo:27017"
DB_NAME = "platform_db"

async def list_creds():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db["credentials"]

    print(f"--- Listing Credentials ---")
    async for doc in collection.find({}):
        print(f"Label: {doc.get('label')}")
        print(f"Username: {doc.get('username')}")
        print(f"Metadata: {doc.get('metadata')}")
        print("-" * 20)

    client.close()

if __name__ == "__main__":
    asyncio.run(list_creds())
