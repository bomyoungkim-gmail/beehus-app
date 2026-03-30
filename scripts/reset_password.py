import asyncio
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from core.models.mongo_models import User
from core.auth import get_password_hash
from core.config import settings

async def main():
    print("🔌 Conectando ao MongoDB para recuperar senha...")
    client = AsyncIOMotorClient(settings.MONGO_URI)
    await init_beanie(database=client[settings.MONGO_DB_NAME], document_models=[User])

    email = input("Digite o Email do usuário: ").strip()
    if not email:
        print("❌ O Email é obrigatório.")
        return

    new_password = input("Digite a nova Senha: ").strip()
    if not new_password:
        print("❌ A Senha é obrigatória.")
        return

    user = await User.find_one(User.email == email)
    if not user:
        print(f"❌ Usuário com o email '{email}' não foi encontrado.")
        return

    user.password_hash = get_password_hash(new_password)
    await user.save()
    print(f"✅ Senha do usuário '{email}' foi redefinida com sucesso!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
    except Exception as e:
        print(f"\n❌ Erro: {e}")
