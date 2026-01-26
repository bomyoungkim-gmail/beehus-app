import asyncio
import sys
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from core.models.mongo_models import User
from core.auth import get_password_hash
from core.config import settings

async def main():
    # Connect to DB
    print("🔌 Connecting to MongoDB...")
    client = AsyncIOMotorClient(settings.MONGO_URI)
    await init_beanie(database=client[settings.MONGO_DB_NAME], document_models=[User])

    # Input
    print("\n--- Create New User ---")
    email = input("Email: ").strip()
    if not email:
        print("❌ Email is required.")
        return

    password = input("Password: ").strip()
    if not password:
        print("❌ Password is required.")
        return
    
    full_name = input("Full Name (optional): ").strip()

    # Check existing
    existing = await User.find_one(User.email == email)
    if existing:
        print(f"❌ User with email {email} already exists.")
        return

    # Create
    user = User(
        email=email,
        password_hash=get_password_hash(password),
        full_name=full_name if full_name else None,
        role="user"
    )
    await user.save()
    print(f"✅ User {email} created successfully!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
