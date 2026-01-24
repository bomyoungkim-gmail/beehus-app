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
from core.utils.date_utils import get_previous_business_day, get_now, get_today

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
                timestamped_msg = f"[{get_now().time()}] {msg}"
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
    
    def _get_business_day(
        self,
        region: str = "BR",
        state: str = "SP",
        days: int = 1,
        fmt: str = "%d/%m/%Y",
    ) -> str:
        """
        Obtém o dia útil anterior.

        Returns:
            Data formatada pelo formato informado.
        """
        previous_day = get_previous_business_day(
            ref_date=get_today(),
            region=region,
            state=state,
            days=days
        )
        return previous_day.strftime(fmt)

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


    async def _get_report_date(self, params: Dict[str, Any], log_func) -> str:
        """Resolve a data do relatorio a partir dos parametros."""
        business_day = self._get_business_day()
        if params.get("use_business_day") and params.get("business_day"):
            parsed_date = self._parse_report_date(params.get("business_day"))
            if parsed_date:
                business_day = parsed_date
            else:
                await log_func("INFO Data informada invalida, usando dia util anterior.")
        await log_func(f"INFO Data do relatorio: {business_day}")
        return business_day

    async def _get_extrato_period(
        self,
        params: Dict[str, Any],
        business_day: str,
        log_func,
    ) -> Optional[tuple[str, str]]:
        """Resolve periodo do extrato, usando business_day quando necessario."""
        extrato_enabled = params.get("extrato") or params.get("export_extrato")
        if not extrato_enabled:
            return None

        extrato_start = params.get("extrato_start_date") or business_day
        extrato_end = params.get("extrato_end_date") or business_day
        parsed_start = self._parse_report_date(extrato_start)
        parsed_end = self._parse_report_date(extrato_end)
        if not parsed_start or not parsed_end:
            await log_func("INFO Data do extrato invalida, usando dia util anterior.")
            parsed_start = business_day
            parsed_end = business_day

        return parsed_start, parsed_end
    
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
                f"ERROR Erro durante o login Itau Onshore: {error_msg}\n"
                f"Agencia: {credentials.agency}\n"
                f"Conta: {credentials.account}"
            )
        else:
            await log_func(f"ERROR Erro durante o login Itau Onshore: {error_msg}")
        
        # Captura screenshot para debug
        try:
            timestamp = get_now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/artifacts/error_itauonshore_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            await log_func(f"SCREEN Screenshot salvo em: {screenshot_path}")
        except Exception as ss_e:
            await log_func(f"WARN Falha ao salvar screenshot: {ss_e}")
        
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
            await log(f"ERROR {error_msg}")
            await log(f"INFO Available params: {list(params.keys())}")
            return self._error_result(run_id, error_msg)
        
        # Criar actions
        actions = self._create_actions(driver, log)
        
        try:
            # ========== FLUXO PRINCIPAL ==========
            
            # Resolve parameters
            export_holdings = params.get('export_holdings', True)
            export_history = params.get('export_history', False)
            
            # Initial Date Calculation (for registration robustness)
            holdings_date = None
            history_date = None
            
            if export_holdings:
                from core.connectors.utils.date_calculator import calculate_holdings_date
                holdings_date = calculate_holdings_date(params, output_format="%d/%m/%Y")
            
            if export_history:
                from core.connectors.utils.date_calculator import calculate_history_date
                history_date = calculate_history_date(params, output_format="%d/%m/%Y")

            await log(f"DEBUG Params Resolved - Holdings: {export_holdings} ({holdings_date}), History: {export_history} ({history_date})")

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
            if export_holdings:
                 await actions.open_menu()
                 await actions.navigate_to_posicao_diaria()
                 await log(f"INFO Holdings date: {holdings_date}")
                 await actions.set_report_date(holdings_date)
                 await actions.export_holdings()
            
            # 4. Export History (if enabled)
            if export_history and history_date:
                await log(f"INFO History date: {history_date}")
                # For Itau, history needs start and end dates (same date for single day)
                await actions.open_menu()
                await actions.navigate_to_conta_corrente()
                await actions.open_extrato()
                await actions.set_extrato_date_range(history_date, history_date)
                await actions.apply_extrato_filter()
                await actions.export_history()


            # Save dates to run
            if run:
                update_data = {}
                # Position Date
                holdings_date = locals().get("holdings_date")
                if holdings_date:
                    update_data["report_date"] = holdings_date
                
                # History Date
                history_date = locals().get("history_date")
                if history_date:
                     update_data["history_date"] = history_date

                if update_data:
                    await run.update({"$set": update_data})
            
            await log("Sleeping for 10s for visual verification...")
            await asyncio.sleep(10)

            # 5. Logout (safe attempt)
            try:
                await actions.logout()
            except Exception as e:
                await log(f"WARN Logout failed (non-critical): {e}")

            return self._success_result(run_id, credentials.cpf)
            
        except Exception as e:
            # Attempt to save dates if they were calculated before error
            try:
                if run:
                    update_data = {}
                    holdings_date = locals().get("holdings_date")
                    history_date = locals().get("history_date")
                    
                    # Fallback for Itau if nothing calculated yet, try business_day
                    if not holdings_date and not history_date:
                         # Only set report_date (Position) as generic fallback
                         update_data["report_date"] = self._get_business_day()
                    else:
                        if holdings_date:
                            update_data["report_date"] = holdings_date
                        if history_date:
                            update_data["history_date"] = history_date
                    
                    if update_data:
                        await run.update({"$set": update_data})
            except Exception:
                pass

            # Log error FIRST before trying to logout
            await log(f"ERROR Exception caught: {e}")
            import traceback
            await log(f"ERROR Traceback: {traceback.format_exc()}")

            # 5. Logout (safe attempt)
            try:
                await actions.logout()
            except Exception as logout_e:
                await log(f"WARN Logout failed: {logout_e}")

            return await self._handle_error(e, driver, run_id, log, credentials)

    

    
