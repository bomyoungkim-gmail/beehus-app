"""
Script para encontrar elementos clicáveis com data (não inputs).
Procura por spans, divs, buttons com texto de data.
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def find_date_elements():
    """Identifica elementos clicáveis com data."""
    from core.db import init_db
    from core.models.mongo_models import Workspace, Credential
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from core.connectors.helpers.selenium_helpers import SeleniumHelpers
    from core.connectors.seletores.itau_onshore import SeletorItauOnshore
    from core.connectors.actions.itau_onshore_actions import ItauOnshoreActions
    from core.security import decrypt_value
    
    await init_db()
    
    print("=" * 70)
    print("PROCURANDO ELEMENTOS DE DATA (NÃO INPUTS)")
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
        print("PROCURANDO ELEMENTOS COM PADRÃO DE DATA")
        print("=" * 70)
        print()
        
        # Aguarda página carregar
        await asyncio.sleep(3)
        
        # Procura por elementos que contenham padrão de data DD/MM/YYYY
        date_pattern_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '/2026') or contains(text(), '/01/')]")
        
        print(f"Elementos com padrão de data encontrados: {len(date_pattern_elements)}")
        print()
        
        for i, elem in enumerate(date_pattern_elements, 1):
            try:
                tag = elem.tag_name
                text = elem.text.strip()
                classes = elem.get_attribute("class") or "N/A"
                clickable = elem.get_attribute("onclick") or elem.get_attribute("ng-click") or "N/A"
                visible = elem.is_displayed()
                
                print(f"Elemento #{i}:")
                print(f"  Tag: {tag}")
                print(f"  Text: {text[:100]}")
                print(f"  Classes: {classes[:100]}")
                print(f"  Clickable: {clickable[:100]}")
                print(f"  Visible: {visible}")
                
                # Tenta obter XPath
                try:
                    xpath = driver.execute_script("""
                        function getXPath(element) {
                            if (element.id !== '')
                                return '//*[@id="' + element.id + '"]';
                            if (element === document.body)
                                return '/html/body';
                            var ix = 0;
                            var siblings = element.parentNode.childNodes;
                            for (var i = 0; i < siblings.length; i++) {
                                var sibling = siblings[i];
                                if (sibling === element)
                                    return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                                if (sibling.nodeType === 1 && sibling.tagName === element.tagName)
                                    ix++;
                            }
                        }
                        return getXPath(arguments[0]);
                    """, elem)
                    print(f"  XPath: {xpath}")
                except:
                    print(f"  XPath: N/A")
                
                print()
                
            except Exception as e:
                print(f"Elemento #{i}: Erro - {e}")
                print()
        
        # Procura especificamente por "14/01/2026"
        print("=" * 70)
        print("PROCURANDO ESPECIFICAMENTE '14/01/2026'")
        print("=" * 70)
        print()
        
        specific_date_elems = driver.find_elements(By.XPATH, "//*[contains(text(), '14/01/2026')]")
        print(f"Elementos com '14/01/2026': {len(specific_date_elems)}")
        print()
        
        for i, elem in enumerate(specific_date_elems, 1):
            try:
                print(f"Elemento #{i}:")
                print(f"  Tag: {elem.tag_name}")
                print(f"  Text: {elem.text}")
                print(f"  ID: {elem.get_attribute('id') or 'N/A'}")
                print(f"  Class: {elem.get_attribute('class') or 'N/A'}")
                print(f"  Clickable: {elem.is_enabled()}")
                print(f"  Visible: {elem.is_displayed()}")
                
                # Tenta clicar para ver se abre algo
                if elem.is_displayed() and elem.is_enabled():
                    print(f"  -> Tentando clicar...")
                    elem.click()
                    await asyncio.sleep(2)
                    
                    # Tira screenshot após clicar
                    screenshot_path = f"/app/artifacts/after_click_date_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    driver.save_screenshot(screenshot_path)
                    print(f"  -> Screenshot após click: {screenshot_path}")
                    
                    # Procura por inputs que apareceram
                    new_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']:not([type='hidden'])")
                    print(f"  -> Inputs visíveis após click: {len(new_inputs)}")
                    for j, inp in enumerate(new_inputs, 1):
                        if inp.is_displayed():
                            print(f"     Input #{j}: id='{inp.get_attribute('id')}' placeholder='{inp.get_attribute('placeholder')}'")
                
                print()
                
            except Exception as e:
                print(f"  Erro: {e}")
                print()
        
        # Screenshot final
        screenshot_path = f"/app/artifacts/date_elements_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        driver.save_screenshot(screenshot_path)
        print(f"[SCREENSHOT] Final: {screenshot_path}")
        
        # Aguarda
        print()
        print("Aguardando 30 segundos...")
        await asyncio.sleep(30)
        
    finally:
        driver.quit()
        print("[INFO] Browser fechado")


if __name__ == "__main__":
    asyncio.run(find_date_elements())
