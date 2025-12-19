import asyncio
import sys
import os

sys.path.append(os.getcwd())

from core.db import init_db
from core.models.mongo_models import User
from core.auth import get_password_hash

async def create_user():
    await init_db()
    
    email = "admin@beehus.io"
    password = "password"
    
    existing = await User.find_one({"email": email})
    if existing:
        print(f"User {email} already exists.")
        return

    user = User(
        email=email,
        password_hash=get_password_hash(password),
        full_name="Admin User",
        role="admin"
    )
    await user.save()
    print(f"✅ User created: {email} / {password}")

if __name__ == "__main__":
    asyncio.run(create_user())
