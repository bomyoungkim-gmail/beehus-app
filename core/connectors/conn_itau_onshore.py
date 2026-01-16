"""
Conector Itaú Onshore - Versão Refatorada
Estrutura modular para facilitar manutenção e reutilização.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.base import BaseConnector
from core.schemas.messages import ScrapeResult
from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.itau_onshore import SeletorItauOnshore
from core.connectors.actions.itau_onshore_actions import ItauOnshoreActions
from core.utils.date_utils import get_previous_business_day

logger = logging.getLogger(__name__)


@dataclass
class ItauCredentials:
    """Credenciais para acesso ao Itaú Onshore."""
    agency: str
    account: str
    cpf: str
    password: str


class ItauOnshoreConnector(BaseConnector):
    """Conector para automação do portal Itaú Onshore."""
    
    @property
    def name(self) -> str:
        return "itau_onshore_login"
    
    # ========== SETUP E HELPERS ==========
    
    def _make_run_logger(self, logger, run):
        """
        Cria função de log que registra tanto no logger quanto no run.
        
        Args:
            logger: Logger instance
            run: Run model instance (pode ser None)
            
        Returns:
            Função assíncrona de log
        """
        async def log(msg: str):
            logger.info(f"[Itau Onshore] {msg}")
            if run:
                timestamped_msg = f"[{datetime.now().time()}] {msg}"
                await run.update({"$push": {"logs": timestamped_msg}})
        return log
    
    async def _setup_run(self, params: Dict[str, Any]):
        """
        Inicializa o run e função de log.
        
        Args:
            params: Parâmetros do scrape
            
        Returns:
            Tupla (run, log_function)
        """
        from core.models.mongo_models import Run
        
        run_id = params.get("run_id")
        run = await Run.get(run_id) if run_id else None
        log = self._make_run_logger(logger, run)
        
        return run, log
    
    def _validate_credentials(self, params: Dict[str, Any]) -> Optional[ItauCredentials]:
        """
        Valida e extrai credenciais dos parâmetros.
        
        Args:
            params: Parâmetros do scrape
            
        Returns:
            ItauCredentials se válido, None caso contrário
        """
        agency = params.get("agencia")
        account = params.get("conta_corrente") or params.get("conta")
        cpf = params.get("username") or params.get("user")
        password = params.get("password") or params.get("pass")
        
        if not all([agency, account, cpf, password]):
            return None
        
        return ItauCredentials(
            agency=agency,
            account=account,
            cpf=cpf,
            password=password
        )
    
    def _create_actions(
        self,
        driver: WebDriver,
        log_func
    ) -> ItauOnshoreActions:
        """
        Cria instância de ItauOnshoreActions.
        
        Args:
            driver: WebDriver instance
            log_func: Função de log
            
        Returns:
            ItauOnshoreActions instance
        """
        helpers = SeleniumHelpers(driver, timeout=50)
        selectors = SeletorItauOnshore()
        
        return ItauOnshoreActions(driver, helpers, selectors, log_func)
    
    def _get_business_day(self) -> str:
        """
        Obtém o dia útil anterior.
        
        Returns:
            Data formatada DD/MM/YYYY
        """
        previous_day = get_previous_business_day(
            ref_date=datetime.today().date(),
            region="BR",
            state="SP",
            days=1
        )
        return previous_day.strftime("%d/%m/%Y")

    def _parse_report_date(self, date_str: str) -> Optional[str]:
        """
        Normaliza datas para DD/MM/YYYY.

        Aceita DD/MM/YYYY ou YYYY-MM-DD.
        """
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return None

    
    def _success_result(self, run_id: Optional[str], cpf: str) -> ScrapeResult:
        """Cria resultado de sucesso."""
        return ScrapeResult(
            run_id=run_id,
            success=True,
            data={"message": "Logged in successfully", "cpf": cpf}
        )
    
    def _error_result(self, run_id: Optional[str], error: str) -> ScrapeResult:
        """Cria resultado de erro."""
        return ScrapeResult(
            run_id=run_id,
            success=False,
            error=error
        )
    
    async def _handle_error(
        self,
        e: Exception,
        driver: WebDriver,
        run_id: Optional[str],
        log_func,
        credentials: Optional[ItauCredentials] = None
    ) -> ScrapeResult:
        """
        Trata erros durante a execução.
        
        Args:
            e: Exceção capturada
            driver: WebDriver instance
            run_id: ID do run
            log_func: Função de log
            credentials: Credenciais (opcional, para log)
            
        Returns:
            ScrapeResult com erro
        """
        error_msg = str(e)
        if credentials:
            await log_func(
                f"❌ Erro durante o login Itau Onshore: {error_msg}\n"
                f"Agencia: {credentials.agency}\n"
                f"Conta: {credentials.account}"
            )
        else:
            await log_func(f"❌ Erro durante o login Itau Onshore: {error_msg}")
        
        # Captura screenshot para debug
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/artifacts/error_itauonshore_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            await log_func(f"📸 Screenshot salvo em: {screenshot_path}")
        except Exception as ss_e:
            await log_func(f"⚠️ Falha ao salvar screenshot: {ss_e}")
        
        # Pausa para inspeção visual via VNC
        await log_func("⏸️ Pausando por 120s para inspeção visual (erro)...")
        await asyncio.sleep(120)
        
        return self._error_result(run_id, error_msg)
    
    # ========== MÉTODO PRINCIPAL ==========
    
    async def scrape(self, driver: WebDriver, params: Dict[str, Any]) -> ScrapeResult:
        """
        Executa o fluxo completo de scraping do Itaú Onshore.
        
        Args:
            driver: WebDriver instance
            params: Parâmetros incluindo credenciais e run_id
            
        Returns:
            ScrapeResult com sucesso ou erro
        """
        # Setup
        run, log = await self._setup_run(params)
        run_id = params.get("run_id")
        
        logger.info(f"Starting Itau Login with params: {params}")
        
        # Validação de credenciais
        credentials = self._validate_credentials(params)
        if not credentials:
            error_msg = "Missing credentials - check username, password, agencia, and conta"
            logger.error(error_msg)
            await log(f"❌ {error_msg}")
            await log(f"📋 Available params: {list(params.keys())}")
            return self._error_result(run_id, error_msg)
        
        # Criar actions
        actions = self._create_actions(driver, log)
        
        try:
            # ========== FLUXO PRINCIPAL ==========
            
            # 1. Navegação e Login
            await actions.navigate_to_login(SeletorItauOnshore.URL_BASE)
            await actions.open_more_access_modal()
            await actions.fill_agency_and_account(credentials.agency, credentials.account)
            await actions.submit_access()
            
            # 2. Autenticação
            await actions.select_assessores_profile()
            await actions.fill_cpf(credentials.cpf)
            await actions.submit_cpf()
            await actions.fill_password_keyboard(credentials.password)
            await actions.submit_password()
            
            # 3. Navegação para Posição Diária
            await actions.open_menu()
            await actions.navigate_to_posicao_diaria()
            
            # 4. Configuração e Exportação de Relatório
            business_day = self._get_business_day()
            if params.get("use_business_day") and params.get("business_day"):
                parsed_date = self._parse_report_date(params.get("business_day"))
                if parsed_date:
                    business_day = parsed_date
                else:
                    await log("?? Data informada invalida, usando dia util anterior.")
            await log(f"?? Data do relat¢rio: {business_day}")
            await actions.set_report_date(business_day)
            await actions.export_to_excel()
            
            # ========== SUCESSO ==========
            
            await log("✅ Login Success! Sleeping for 120s for visual verification...")
            await asyncio.sleep(120)
            
            return self._success_result(run_id, credentials.cpf)
            
        except Exception as e:
            return await self._handle_error(e, driver, run_id, log, credentials)

    
        # 5. Logout
        await actions.logout()
    