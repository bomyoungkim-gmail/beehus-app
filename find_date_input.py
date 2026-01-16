"""
Script para identificar o seletor correto do campo de data.
Navega até a página e lista todos os inputs disponíveis.
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def find_date_input():
    """Identifica o campo de data correto."""
    from core.db import init_db
    from core.models.mongo_models import Workspace, Credential, Job
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from core.connectors.conn_itau_onshore import ItauOnshoreConnector
    from core.connectors.helpers.selenium_helpers import SeleniumHelpers
    from core.connectors.seletores.itau_onshore import SeletorItauOnshore
    from core.connectors.actions.itau_onshore_actions import ItauOnshoreActions
    from core.security import decrypt_value
    
    await init_db()
    
    print("=" * 70)
    print("IDENTIFICANDO CAMPO DE DATA")
    print("=" * 70)
    print()
    
    # Busca credenciais
    workspace = await Workspace.find_one({"name": "Demo Workspace"})
    credential = await Credential.find_one({
        "workspace_id": workspace.id,
        "label": {"$regex": "itau|chc", "$options": "i"}
    })
    
    password = decrypt_value(credential.encrypted_password)
    conta = credential.metadata.get("conta") or credential.metadata.get("conta_corrente", "")
    agencia = credential.metadata.get("agencia", "")
    
    # Configura Selenium
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Remote(
        command_executor="http://selenium:4444/wd/hub",
        options=chrome_options
    )
    
    try:
        helpers = SeleniumHelpers(driver)
        sel = SeletorItauOnshore()
        
        async def log(msg):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        
        actions = ItauOnshoreActions(driver, helpers, sel, log)
        
        # Faz login
        print("[INFO] Fazendo login...")
        await actions.navigate_to_login(sel.URL_BASE)
        await actions.open_more_access_modal()
        await actions.fill_agency_and_account(agencia, conta)
        await actions.submit_access()
        await actions.select_assessores_profile()
        await actions.fill_cpf(credential.username)
        await actions.submit_cpf()
        await actions.fill_password_keyboard(password)
        await actions.submit_password()
        await actions.open_menu()
        await actions.navigate_to_posicao_diaria()
        
        print()
        print("=" * 70)
        print("PÁGINA CARREGADA - ANALISANDO INPUTS")
        print("=" * 70)
        print()
        
        # Aguarda página carregar
        await asyncio.sleep(3)
        
        # Lista TODOS os inputs na página
        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        print(f"Total de inputs encontrados: {len(all_inputs)}")
        print()
        
        for i, inp in enumerate(all_inputs, 1):
            try:
                tag = inp.tag_name
                inp_type = inp.get_attribute("type") or "N/A"
                placeholder = inp.get_attribute("placeholder") or "N/A"
                name = inp.get_attribute("name") or "N/A"
                id_attr = inp.get_attribute("id") or "N/A"
                classes = inp.get_attribute("class") or "N/A"
                value = inp.get_attribute("value") or "N/A"
                formcontrolname = inp.get_attribute("formcontrolname") or "N/A"
                idsmask = inp.get_attribute("idsmask") or "N/A"
                visible = inp.is_displayed()
                
                print(f"Input #{i}:")
                print(f"  Type: {inp_type}")
                print(f"  ID: {id_attr}")
                print(f"  Name: {name}")
                print(f"  Placeholder: {placeholder}")
                print(f"  Value: {value}")
                print(f"  FormControlName: {formcontrolname}")
                print(f"  IdsMask: {idsmask}")
                print(f"  Classes: {classes[:80]}")
                print(f"  Visible: {visible}")
                print()
                
            except Exception as e:
                print(f"Input #{i}: Erro ao ler - {e}")
                print()
        
        # Tira screenshot
        screenshot_path = f"/app/artifacts/date_inputs_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        driver.save_screenshot(screenshot_path)
        print(f"[SCREENSHOT] Salvo: {screenshot_path}")
        
        # Aguarda para inspeção manual
        print()
        print("=" * 70)
        print("Aguardando 60 segundos para inspeção manual...")
        print("Acesse http://localhost:7900 (senha: secret) para ver o browser")
        print("=" * 70)
        await asyncio.sleep(60)
        
    finally:
        driver.quit()
        print("[INFO] Browser fechado")


if __name__ == "__main__":
    asyncio.run(find_date_input())
