"""
Módulo de ações específicas para o conector Itaú Onshore.
Encapsula toda a lógica de interação com o portal em métodos reutilizáveis.
"""

import asyncio
from typing import Callable
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select
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

    def _click_with_fallback(self, locator) -> bool:
        try:
            self.helpers.click_element(*locator)
            return True
        except Exception:
            pass

        try:
            elements = self.driver.find_elements(*locator)
            for el in elements:
                if el.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    self.driver.execute_script("arguments[0].click();", el)
                    return True
        except Exception:
            pass

        return False

    def _find_in_default_or_iframes(self, locator, timeout: int = 20):
        """
        Find element in current/other windows and nested iframe/frame trees.
        Keeps driver in the exact context where element was found.
        """
        by, value = locator

        def _try_find_visible_here():
            for el in self.driver.find_elements(by, value):
                if el.is_displayed():
                    return el
            return None

        def _search_frames_recursive(depth: int = 0):
            if depth > 6:
                return None

            found = _try_find_visible_here()
            if found:
                return found

            frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe,frame")
            for frame in frames:
                try:
                    self.driver.switch_to.frame(frame)
                except Exception:
                    continue
                try:
                    nested = _search_frames_recursive(depth + 1)
                    if nested:
                        return nested
                except Exception:
                    pass
                try:
                    self.driver.switch_to.parent_frame()
                except Exception:
                    self.driver.switch_to.default_content()
            return None

        import time
        end_time = time.time() + timeout
        while time.time() < end_time:
            for handle in self.driver.window_handles:
                try:
                    self.driver.switch_to.window(handle)
                    self.driver.switch_to.default_content()
                except Exception:
                    continue
                found = _search_frames_recursive(0)
                if found:
                    return found
            # small polling interval for dynamic page/frame load
            time.sleep(0.4)

        try:
            self.driver.switch_to.default_content()
        except Exception:
            pass
        return None
    
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
        await self.log("OK Modal aberto")
    
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
        
        await self.log("OK Agência e conta preenchidas")
    
    async def submit_access(self) -> None:
        """Clica no botão de acessar após preencher agência e conta."""
        await self.log("Clicando em Acessar...")
        if not self._click_with_fallback(self.sel.SUBMIT_MORE_ACCESS):
            await self.log("Fallback: Tentando botão alternativo...")
            self._click_with_fallback(self.sel.ACCESS_FALLBACK)
        await self.log("OK Acesso enviado")
    
    async def select_assessores_profile(self) -> None:
        """Seleciona o perfil de Assessores."""
        await self.log("Selecionando perfil Assessores...")
        if not self._click_with_fallback(self.sel.ASSESSORES_BTN):
            await self.log("Fallback: Tentando link ASSESSORES...")
            self._click_with_fallback(self.sel.ASSESSORES_LINK)
        await self.log("OK Perfil Assessores selecionado")
    
    async def fill_cpf(self, cpf: str) -> None:
        """
        Preenche o campo de CPF.
        
        Args:
            cpf: CPF do assessor
        """
        await self.log(f"Preenchendo CPF: {cpf[:3]}.***.***-**")
        self.helpers.send_keys(*self.sel.CPF, cpf)
        await self.log("OK CPF preenchido")
    
    async def submit_cpf(self) -> None:
        """Clica no botão de submit após preencher o CPF."""
        await self.log("Enviando CPF...")
        self._click_with_fallback(self.sel.SUBMIT_BTN)
        await self.log("OK CPF enviado")
    
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
        
        await self.log("OK Senha preenchida")
    
    async def submit_password(self) -> None:
        """Clica no botão de continuar após preencher a senha."""
        await self.log("Enviando senha...")
        self._click_with_fallback(self.sel.SUBMIT_BTN)
        await self.log("OK Senha enviada")
    
    # ========== MENU E NAVEGAÇÃO INTERNA ==========
    
    async def open_menu(self) -> None:
        """Abre o menu principal (hover)."""
        await self.log("Abrindo menu principal...")
        self.helpers.hover_element(*self.sel.MENU)
        await self.log("OK Menu aberto")

    async def ensure_menu_open(self) -> None:
        """Garante que o menu principal esteja aberto antes de navegar em itens internos."""
        try:
            menu = self.helpers.wait_for_element(*self.sel.MENU)
            expanded = (menu.get_attribute("aria-expanded") or "").strip().lower() == "true"
            if expanded:
                await self.log("INFO Menu ja estava aberto")
                return
        except Exception:
            await self.log("WARN Nao foi possivel verificar estado do menu. Tentando abrir...")

        await self.open_menu()
    
    async def navigate_to_posicao_diaria(self) -> None:
        """Navega para a página de Posição Diária."""
        await self.log("Navegando para Posição Diária...")
        self._click_with_fallback(self.sel.POSICAO_DIARIA)

        await self.log("OK Posição Diária carregada")
    
    async def navigate_to_conta_corrente(self) -> bool:
        """Navega para a pagina de Conta Corrente."""
        await self.log("Navegando para Conta Corrente...")
        clicked = self._click_with_fallback(self.sel.CONTA_CORRENTE)
        if not clicked:
            await self.log("WARN Link 'conta corrente' nao encontrado")
            return False

        # Evita falso positivo: só confirma sucesso se algum elemento de Extrato ficar visível
        # após o clique em conta corrente.
        try:
            self.helpers.wait_until(
                lambda d: any(
                    el.is_displayed()
                    for el in self.driver.find_elements(*self.sel.EXTRATO)
                ),
                timeout=8,
            )
            await self.log("OK Conta Corrente carregada")
            return True
        except Exception:
            await self.log("WARN Clique em 'conta corrente' nao abriu area de extrato")
            return False

    async def open_extrato(self) -> None:
        """Abre a pagina de Extrato."""
        await self.log("Abrindo extrato...")
        self._click_with_fallback(self.sel.EXTRATO)
        await self.log("OK Extrato aberto")

    async def set_extrato_date_range(self, start_date: str, end_date: str) -> None:
        """Define data inicial e final do extrato."""
        await self.log("Selecionando periodo personalizado...")
        self._click_with_fallback(self.sel.EXTRATO_PERIODO_TRIGGER)
        option = self.helpers.wait_for_visible(*self.sel.EXTRATO_PERIODO_PERSONALIZADO)
        self.helpers.wait_until(lambda d: option.is_enabled())
        option.click()

        await self.log(f"Definindo periodo do extrato: {start_date} - {end_date}")
        self.helpers.clear_and_send_keys(*self.sel.EXTRATO_DATE_INICIAL, start_date)
        self.helpers.clear_and_send_keys(*self.sel.EXTRATO_DATE_FINAL, end_date)
        await self.log("OK Periodo do extrato definido")

    async def apply_extrato_filter(self) -> None:
        """Aplica filtro do extrato."""
        await self.log("Aplicando filtro do extrato...")
        btn = self.helpers.find_element(*self.sel.EXTRATO_FILTRAR)
        self.helpers.wait_until(lambda d: btn.is_enabled())
        btn.click()
        self.helpers.wait_for_invisibility(*self.sel.EXTRATO_LOADING)
        # Aguarda atualizacao da pagina/resultado
        export_menu = self.helpers.find_element(*self.sel.EXTRATO_EXPORT_MENU)
        self.helpers.wait_until(lambda d: export_menu.is_displayed() and export_menu.is_enabled())
        await self.log("OK Filtro aplicado")

    async def export_history(self) -> None:
        """Exporta extrato para Excel."""
        await self.log("Exportando extrato para Excel...")
        # Aguarda o loading sumir para nao interceptar o clique
        self.helpers.wait_for_invisibility(*self.sel.EXTRATO_LOADING)
        self._click_with_fallback(self.sel.EXTRATO_EXPORT_MENU)
        self._click_with_fallback(self.sel.EXTRATO_EXPORT_EXCEL)

        try:
            checks = self.driver.find_elements(*self.sel.EXTRATO_EXCEL_CHECKBOXES)
            for chk in checks:
                if chk.is_displayed() and chk.is_enabled() and not chk.is_selected():
                    chk.click()
        except Exception:
            pass

        self._click_with_fallback(self.sel.EXTRATO_EXCEL_SAVE)
        await self.log("OK Exportacao do extrato iniciada")
        await self.log("Aguardando 15s para download...")
        await asyncio.sleep(15)

    async def export_history_fallback_pix_pdf(self) -> bool:
        """
        Fallback para histórico quando o link 'conta corrente' não estiver disponível.
        Fluxo:
        ver mais -> extrato -> dropdown produto -> continuar -> extrato pix -> salvar em pdf.
        """
        await self.log("INFO Iniciando fallback de historico (Pix/PDF)...")
        await self.ensure_menu_open()

        if not self._click_with_fallback(self.sel.VER_MAIS):
            await self.log("WARN Fallback: nao encontrou 'ver mais'")
            return False
        await self.log("OK Fallback: clicou em 'ver mais'")

        if not self._click_with_fallback(self.sel.EXTRATO_FALLBACK):
            await self.log("WARN Fallback: nao encontrou link 'extrato'")
            return False
        await self.log("OK Fallback: clicou em 'extrato'")

        try:
            # Alguns fluxos antigos do Itau abrem nova janela ao entrar no extrato.
            try:
                handles = self.driver.window_handles
                if len(handles) > 1:
                    self.driver.switch_to.window(handles[-1])
                    await self.log("INFO Fallback: alternou para nova janela de extrato")
            except Exception:
                pass

            # Aguarda renderizar pagina de extrato fallback.
            await asyncio.sleep(1.5)
            dropdown = self._find_in_default_or_iframes(self.sel.PRODUTO_DROPDOWN, timeout=20)
            if dropdown is None:
                await self.log("WARN Fallback: dropdown de produto nao encontrado")
                return False

            self.helpers.wait_until(lambda d: dropdown.is_displayed() and dropdown.is_enabled(), timeout=8)
            select = Select(dropdown)

            selected = ""
            try:
                select.select_by_value("id:10416")
                selected = "id:10416"
            except Exception:
                try:
                    select.select_by_visible_text("Poupança")
                    selected = "Poupança"
                except Exception:
                    try:
                        select.select_by_value("id:10417")
                        selected = "id:10417"
                    except Exception:
                        # JS fallback by value/text contains
                        selected = self.driver.execute_script(
                            """
                            const s = arguments[0];
                            if (!s) return '';
                            const opts = Array.from(s.options || []);
                            let opt = opts.find(o => (o.value || '').trim() === 'id:10416');
                            if (!opt) opt = opts.find(o => (o.textContent || '').toLowerCase().includes('poup'));
                            if (!opt) opt = opts.find(o => (o.value || '').trim() === 'id:10417');
                            if (!opt) opt = opts.find(o => (o.textContent || '').toLowerCase().includes('previd'));
                            if (!opt) return '';
                            s.value = opt.value;
                            s.dispatchEvent(new Event('change', { bubbles: true }));
                            return opt.value || (opt.textContent || '').trim();
                            """,
                            dropdown,
                        ) or ""

            if not selected:
                await self.log("WARN Fallback: nao conseguiu selecionar Poupança/Previdência no dropdown")
                return False

            # Garante onchange para páginas antigas.
            self.driver.execute_script(
                "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                dropdown,
            )
            await self.log(f"OK Fallback: produto selecionado no dropdown ({selected})")
        except Exception as e:
            await self.log(f"WARN Fallback: falha ao selecionar produto no dropdown: {e}")
            return False

        if not self._click_with_fallback(self.sel.CONTINUAR):
            await self.log("WARN Fallback: nao encontrou botao 'Continuar'")
            return False
        await self.log("OK Fallback: clicou em 'Continuar'")

        if not self._click_with_fallback(self.sel.EXTRATO_PIX):
            await self.log("WARN Fallback: nao encontrou botao 'Extrato Pix'")
            return False
        await self.log("OK Fallback: clicou em 'Extrato Pix'")

        if not self._click_with_fallback(self.sel.SALVAR_PDF):
            await self.log("WARN Fallback: nao encontrou botao 'salvar em pdf'")
            return False

        await self.log("OK Fallback: clicou em 'salvar em pdf'")
        await self.log("Aguardando 15s para download PDF...")
        await asyncio.sleep(15)
        return True

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
        
        await self.log("OK Data alterada")
    
    
    
    async def export_holdings(self) -> None:
        """Exporta o relatrio para Excel."""
        await self.log("Exportando para Excel...")
        export_clicked = False

        try:
            self.helpers.click_element_maybe_shadow(*self.sel.EXPORT_EXCEL_BTN)
            export_clicked = True
        except Exception:
            await self.log("Fallback: botao Excel nao encontrado, tentando alternativos...")

        if not export_clicked:
            export_clicked = self._click_with_fallback(self.sel.EXPORT_EXCEL_BTN_ALT)

        if not export_clicked:
            # Fluxo alternativo: selecionar Excel e confirmar download.
            selected_excel = self._click_with_fallback(self.sel.EXCEL)
            clicked_download = self._click_with_fallback(self.sel.BAIXAR)
            export_clicked = selected_excel and clicked_download

        if not export_clicked:
            raise RuntimeError("Nao foi possivel iniciar a exportacao de holdings (botao Excel/Baixar indisponivel).")

        await self.log("OK Exportacao iniciada")
        await self.log("Aguardando 15s para download...")
        await asyncio.sleep(15)

    # ========== LOGOUT ==========

    async def logout(self) -> None:
        """Realiza logout do sistema."""
        await self.log("Iniciando logout...")
        self._click_with_fallback(self.sel.SAIR)
        await self.log("Confirmando logout...")
        self._click_with_fallback(self.sel.SAIR_SIM)
        await self.log(" Logout realizado")
