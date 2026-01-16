"""
Módulo de ações específicas para o conector Itaú Onshore.
Encapsula toda a lógica de interação com o portal em métodos reutilizáveis.
"""

from typing import Callable
from selenium.webdriver.remote.webdriver import WebDriver
from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.itau_onshore import SeletorItauOnshore
from core.connectors.utils.digital_keyboard_utils import build_digit_to_button_map


class ItauOnshoreActions:
    """Encapsula ações específicas do portal Itaú Onshore."""
    
    def __init__(
        self,
        driver: WebDriver,
        helpers: SeleniumHelpers,
        selectors: SeletorItauOnshore,
        log_func: Callable
    ):
        """
        Inicializa as ações do Itaú Onshore.
        
        Args:
            driver: Instância do WebDriver
            helpers: Instância de SeleniumHelpers
            selectors: Instância de SeletorItauOnshore
            log_func: Função assíncrona para logging
        """
        self.driver = driver
        self.helpers = helpers
        self.sel = selectors
        self.log = log_func
    
    # ========== NAVEGAÇÃO ==========
    
    async def navigate_to_login(self, url: str) -> None:
        """Navega para a página de login do Itaú."""
        await self.log(f"NAVIGATE: {url}")
        self.driver.get(url)
    
    async def open_more_access_modal(self) -> None:
        """Abre o modal de acesso com agência e conta."""
        await self.log("Abrindo modal de acesso...")
        self.helpers.click_any_element(
            self.sel.MORE_ACCESS_BTN[0],
            [self.sel.MORE_ACCESS_BTN[1], self.sel.MORE_ACCESS_BTN_ZOOM[1]]
        )
        await self.log("✓ Modal aberto")
    
    # ========== AUTENTICAÇÃO ==========
    
    async def fill_agency_and_account(self, agency: str, account: str) -> None:
        """
        Preenche os campos de agência e conta.
        
        Args:
            agency: Número da agência
            account: Número da conta
        """
        await self.log(f"Preenchendo agência: {agency}")
        self.helpers.send_keys(*self.sel.AGENCY, agency)
        
        await self.log(f"Preenchendo conta: {account}")
        self.helpers.send_keys(*self.sel.ACCOUNT, account)
        
        await self.log("✓ Agência e conta preenchidas")
    
    async def submit_access(self) -> None:
        """Clica no botão de acessar após preencher agência e conta."""
        await self.log("Clicando em Acessar...")
        try:
            self.helpers.click_element(*self.sel.SUBMIT_MORE_ACCESS)
        except Exception:
            await self.log("Fallback: Tentando botão alternativo...")
            self.helpers.click_element(*self.sel.ACCESS_FALLBACK)
        await self.log("✓ Acesso enviado")
    
    async def select_assessores_profile(self) -> None:
        """Seleciona o perfil de Assessores."""
        await self.log("Selecionando perfil Assessores...")
        try:
            self.helpers.click_element(*self.sel.ASSESSORES_BTN)
        except Exception:
            await self.log("Fallback: Tentando link ASSESSORES...")
            self.helpers.click_element(*self.sel.ASSESSORES_LINK)
        await self.log("✓ Perfil Assessores selecionado")
    
    async def fill_cpf(self, cpf: str) -> None:
        """
        Preenche o campo de CPF.
        
        Args:
            cpf: CPF do assessor
        """
        await self.log(f"Preenchendo CPF: {cpf[:3]}.***.***-**")
        self.helpers.send_keys(*self.sel.CPF, cpf)
        await self.log("✓ CPF preenchido")
    
    async def submit_cpf(self) -> None:
        """Clica no botão de submit após preencher o CPF."""
        await self.log("Enviando CPF...")
        self.helpers.click_element(*self.sel.SUBMIT_BTN)
        await self.log("✓ CPF enviado")
    
    async def fill_password_keyboard(self, password: str) -> None:
        """
        Preenche a senha usando o teclado digital.
        
        Args:
            password: Senha numérica
        """
        await self.log("Aguardando teclado digital...")
        self.helpers.wait_for_element(*self.sel.KEYBOARD)
        
        await self.log("Mapeando teclado digital...")
        digit_to_btn = build_digit_to_button_map(self.driver)
        
        await self.log("Preenchendo senha...")
        for digit in password:
            btn = digit_to_btn[digit]
            self.helpers.wait_until(lambda d: btn.is_enabled())
            btn.click()
        
        await self.log("✓ Senha preenchida")
    
    async def submit_password(self) -> None:
        """Clica no botão de continuar após preencher a senha."""
        await self.log("Enviando senha...")
        self.helpers.click_element(*self.sel.SUBMIT_BTN)
        await self.log("✓ Senha enviada")
    
    # ========== MENU E NAVEGAÇÃO INTERNA ==========
    
    async def open_menu(self) -> None:
        """Abre o menu principal (hover)."""
        await self.log("Abrindo menu principal...")
        self.helpers.hover_element(*self.sel.MENU)
        await self.log("✓ Menu aberto")
    
    async def navigate_to_posicao_diaria(self) -> None:
        """Navega para a página de Posição Diária."""
        await self.log("Navegando para Posição Diária...")
        self.helpers.click_element(*self.sel.POSICAO_DIARIA)

        await self.log("✓ Posição Diária carregada")
    
    # ========== RELATÓRIOS ==========
    
    async def set_report_date(self, date_str: str) -> None:
        """
        Define a data do relatório usando o datepicker Angular.
        
        Args:
            date_str: Data no formato DD/MM/YYYY
        """
        await self.log(f"Alterando data para: {date_str}")
        
        self.helpers.set_angular_datepicker(
            trigger_locator=self.sel.DATEPICKER_TRIGGER,
            overlay_locator=self.sel.DATEPICKER_OVERLAY,
            day_selector_template=self.sel.DATEPICKER_DAY_BUTTON,
            day_alt_template=self.sel.DATEPICKER_DAY_ALT,
            confirm_locator=self.sel.DATEPICKER_CONFIRM,
            date_str=date_str
        )
        
        await self.log("✓ Data alterada")
    
    
    
    async def export_to_excel(self) -> None:
        """Exporta o relatrio para Excel."""
        await self.log("Exportando para Excel...")
        try:
            self.helpers.click_element_maybe_shadow(*self.sel.EXPORT_EXCEL_BTN)
        except Exception:
            await self.log("Fallback: botao Excel nao encontrado, tentando alternativos...")
            try:
                self.helpers.click_element(*self.sel.EXPORT_EXCEL_BTN_ALT)
            except Exception:
                # Fluxo alternativo: selecionar Excel e confirmar download
                self.helpers.click_element(*self.sel.EXCEL)
                self.helpers.click_element(*self.sel.BAIXAR)
        await self.log(" Exportaao iniciada")

    # ========== LOGOUT ==========

    async def logout(self) -> None:
        """Realiza logout do sistema."""
        await self.log("Iniciando logout...")
        self.helpers.click_element(*self.sel.SAIR)
        await self.log("Confirmando logout...")
        self.helpers.click_element(*self.sel.SAIR_SIM)
        await self.log(" Logout realizado")
