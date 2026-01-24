from core.connectors.base import BaseConnector
from core.schemas.messages import ScrapeResult
import logging
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ItauOffshoreConnector(BaseConnector):
    @property
    def name(self):
        return "itau_offshore_login"

    async def scrape(self, driver, params: Dict[str, Any]) -> ScrapeResult:
        logger.info(f"Starting Itau Offshore Login with params: {params}")
        
        run_id = params.get("run_id")
        # Support both 'user' (from legacy) and 'username' (from new UI)
        user = params.get("username") or params.get("user")
        password = params.get("password")
        
        # Import models here to avoid circular imports if any, or ensuring context
        from core.models.mongo_models import Run
        from core.db import init_db
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from datetime import datetime
        import asyncio

        # Helper log function (similar to tasks.py)
        run = None
        if run_id:
            # Ensure DB is ready? tasks.py usually already init_db, but safe to ignore if already done
            run = await Run.get(run_id)

        async def log(msg):
            logger.info(f"[JPMorgan] {msg}")
            if run:
                run.logs.append(f"[{datetime.now().time()}] {msg}")
                await run.save()

        _url = "https://ebanking.itauprivatebank.com/auth/login"

        try:
            # 1. Navegação
            await log(f"NAVIGATE: {_url}")
            driver.get(_url)
            
            # 2. Preenchimento de campos
            await log("Waiting for user input field...")
            user_id_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "userId-input-field-input"))
            )
            user_id_field.send_keys(user)
            await log("Typed username")
            
            password_field = driver.find_element(By.ID, "password-input-field-input")
            password_field.send_keys(password)
            await log("Typed password")

            # 3. Click Sign In
            await log("Clicking Sign In...")
            try:
                sign_in_btn = driver.find_element(By.ID, "signin-button")
                sign_in_btn.click()
            except Exception:
                 # Fallback to type=submit if ID changes
                 await log("Fallback: Finding submit button...")
                 sign_in_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                 sign_in_btn.click()
            
            await log("Clicked Sign In")
            
            return ScrapeResult(
                run_id=run_id,
                success=True,
                data={"message": "Logged in successfully", "user": user}
            )

        except Exception as e:
            await log(f"❌ Erro durante o login JPMorgan: {str(e)}")
            
            # Capture Debug Screenshot
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"/app/artifacts/error_jpmorgan_{timestamp}.png"
                driver.save_screenshot(screenshot_path)
                await log(f"📸 Screenshot salvo em: {screenshot_path}")
            except Exception as ss_e:
                await log(f"⚠️ Falha ao salvar screenshot: {ss_e}")
            
            return ScrapeResult(
                run_id=run_id,
                success=False,
                error=str(e)
            )
