"""
Script de teste focado para debugar o erro na aba "Meus investimentos".
Execute: docker compose exec celery-worker python test_itau_connector.py
"""

import asyncio
import sys
import os
from datetime import datetime

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_connector():
    """Testa o connector Itaú Onshore com credenciais do banco."""
    from core.db import init_db
    from core.models.mongo_models import Workspace, Credential, Job, Run
    from core.connectors.conn_itau_onshore import ItauOnshoreConnector
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    
    await init_db()
    
    print("=" * 70)
    print("TESTE DO CONECTOR ITAU ONSHORE")
    print("=" * 70)
    print()
    
    # 1. Busca workspace
    print("[1/5] Buscando workspace...")
    workspace = await Workspace.find_one({"name": "Demo Workspace"})
    if not workspace:
        print("[ERRO] Workspace 'Demo Workspace' não encontrado")
        return
    print(f"[OK] Workspace encontrado: {workspace.name}")
    print()
    
    # 2. Busca credencial do Itaú
    print("[2/5] Buscando credenciais do Itaú...")
    credential = await Credential.find_one({
        "workspace_id": workspace.id,
        "label": {"$regex": "itau|chc", "$options": "i"}
    })
    
    if not credential:
        print("[ERRO] Credencial do Itaú não encontrada")
        # Lista todas as credenciais disponíveis
        all_creds = await Credential.find({"workspace_id": workspace.id}).to_list()
        print(f"\nCredenciais disponíveis ({len(all_creds)}):")
        for i, cred in enumerate(all_creds, 1):
            print(f"  {i}. {cred.label}")
        return
    
    print(f"[OK] Credencial encontrada: {credential.label}")
    print(f"     Username: {credential.username}")
    print()
    
    # 3. Busca job
    print("[3/5] Buscando job do Itaú...")
    job = await Job.find_one({
        "workspace_id": workspace.id,
        "connector": "itau_onshore_login"
    })
    
    if not job:
        print("[AVISO] Job não encontrado, criando parâmetros manualmente...")
        job_params = {}
    else:
        print(f"[OK] Job encontrado: {job.name}")
        job_params = job.params or {}
    print()
    
    # 4. Cria run para logging
    print("[4/5] Criando run para testes...")
    run = Run(
        job_id=job.id if job else "test-run",
        connector="itau_onshore_login",
        status="running",
        started_at=datetime.utcnow()
    )
    await run.insert()
    print(f"[OK] Run criado: {run.id}")
    print()
    
    # 5. Prepara parâmetros
    print("[5/5] Preparando parâmetros do connector...")
    
    # Import decrypt function
    from core.security import decrypt_value
    
    # Descriptografa senha
    try:
        password = decrypt_value(credential.encrypted_password)
        if not password:
            print("[ERRO] Falha ao descriptografar senha")
            return
    except Exception as e:
        print(f"[ERRO] Erro ao descriptografar senha: {e}")
        return
    
    # Busca conta no metadata
    conta = credential.metadata.get("conta") or credential.metadata.get("conta_corrente", "")
    agencia = credential.metadata.get("agencia", "")
    
    if not conta:
        print("[ERRO] Conta não encontrada no metadata")
        print(f"Metadata disponível: {list(credential.metadata.keys())}")
        return
    
    params = {
        "run_id": run.id,
        "agencia": agencia,
        "conta": conta,
        "username": credential.username,
        "password": password,
        **job_params
    }
    
    print(f"Agencia: {params['agencia']}")
    print(f"Conta: {params['conta']}")
    print(f"Username: {params['username']}")
    print(f"Password: {'*' * len(password)}")
    print()
    
    # 6. Configura Selenium
    print("=" * 70)
    print("INICIANDO TESTE COM SELENIUM")
    print("=" * 70)
    print()
    
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # Comentar a linha abaixo para ver o browser
    # chrome_options.add_argument("--headless")
    
    driver = webdriver.Remote(
        command_executor="http://selenium:4444/wd/hub",
        options=chrome_options
    )
    
    try:
        # 7. Executa connector
        connector = ItauOnshoreConnector()
        print(f"[INFO] Executando connector: {connector.name}")
        print()
        
        result = await connector.scrape(driver, params)
        
        print()
        print("=" * 70)
        print("RESULTADO DO TESTE")
        print("=" * 70)
        print(f"Sucesso: {result.success}")
        if result.error:
            print(f"Erro: {result.error}")
        if result.data:
            print(f"Data: {result.data}")
        print()
        
        # Atualiza run
        await run.update({
            "$set": {
                "status": "success" if result.success else "failed",
                "error_summary": result.error,
                "finished_at": datetime.utcnow()
            }
        })
        
        print(f"[OK] Run atualizado com status: {'success' if result.success else 'failed'}")
        print(f"[INFO] Logs do run salvos em: runs/{run.id}")
        
    except Exception as e:
        print()
        print("=" * 70)
        print("ERRO DURANTE EXECUÇÃO")
        print("=" * 70)
        print(f"[ERRO] {e}")
        import traceback
        traceback.print_exc()
        
        # Atualiza run com erro
        await run.update({
            "$set": {
                "status": "failed",
                "error_summary": str(e),
                "finished_at": datetime.utcnow()
            }
        })
        
    finally:
        print()
        print("[INFO] Fechando browser...")
        driver.quit()
        print("[OK] Teste finalizado")
        print()
        print("=" * 70)
        print(f"Para ver os logs completos:")
        print(f"  docker compose exec celery-worker python -c \"")
        print(f"import asyncio")
        print(f"from core.db import init_db")
        print(f"from core.models.mongo_models import Run")
        print(f"async def show():")
        print(f"    await init_db()")
        print(f"    run = await Run.get('{run.id}')")
        print(f"    for log in run.logs:")
        print(f"        print(log)")
        print(f"asyncio.run(show())")
        print(f"  \"")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_connector())
