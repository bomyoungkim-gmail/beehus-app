from dataclasses import dataclass
from selenium.webdriver.common.by import By

@dataclass(frozen=True)
class SeletorItauOnshore:
    """Seletores organizados para o portal Itaú Onshore."""
    
    # URLs
    URL_BASE = "https://www.itau.com.br"
    
    # === LOGIN - Modal de Acesso ===
    MORE_ACCESS_BTN = (By.ID, "open_modal_more_access")
    MORE_ACCESS_BTN_ZOOM = (By.ID, "open-modal-more-access-zoom")
    AGENCY = (By.ID, "idl-more-access-input-agency")
    ACCOUNT = (By.ID, "idl-more-access-input-account")
    SUBMIT_MORE_ACCESS = (By.ID, "idl-more-access-submit-button")
    ACCESS_FALLBACK = (By.CSS_SELECTOR, "button[type='button'][aria-label='Acessar']")
    
    # === AUTHENTICATION - Seleção de Perfil e Credenciais ===
    ASSESSORES_BTN = (By.CSS_SELECTOR, "a[title='Selecionar Assessores'][role='button']")
    ASSESSORES_LINK = (By.LINK_TEXT, "ASSESSORES")
    CPF = (By.ID, "cpf")
    SUBMIT_BTN = (By.ID, "submitBtn")
    KEYBOARD = (By.CSS_SELECTOR, "div.it-auth-keyboard__digits")
    KEYBOARD_DIGIT = (By.CSS_SELECTOR, "button.it-auth-keyboard__digit:not(.it-auth-keyboard__digit--remove)")
    
    # === MENU - Navegação Principal ===
    MENU = (By.CSS_SELECTOR, "a.btn-nav.btn-menu.btn-menubg[onclick*='header:menu']")
    POSICAO_DIARIA = (By.XPATH, "//a[contains(@data-op,'pf-posicao-diaria-investimentos')]")
    CONTA_CORRENTE = (By.XPATH, "//a[normalize-space()='conta corrente']")
    EXTRATO = (By.XPATH, "//a[contains(@aria-label,'extrato') or normalize-space()='extrato']")
    
    # === REPORTS - Relatórios ===
    MEUS_INVESTIMENTOS_TAB = (By.XPATH,
        "//div[contains(@class,'anchor-menu') and @role='tablist']"
        "//button[@role='tab' and normalize-space(.)='Meus investimentos']"
    )
    
    # Datepicker Angular (overlay modal)
    DATEPICKER_TRIGGER = (
        By.CSS_SELECTOR,
        "input[placeholder*='DD/MM'], input[placeholder*='dd/mm'], "
        "input[idsmask*='date'], input[inputmode='none']"
    )
    DATEPICKER_OVERLAY = (By.CSS_SELECTOR, "section.ids-datepicker, .ids-datepicker")
    DATEPICKER_DAY_BUTTON = "//button[@role='checkbox' and contains(@aria-label, '{dia} {mes} {ano}')]"
    DATEPICKER_DAY_ALT = "//button[contains(@class, 'ids-calendar-day') and contains(@aria-label, '{dia} {mes}')]"
    DATEPICKER_CONFIRM = (
        By.XPATH,
        "//button[.//span[normalize-space()='confirmar' or normalize-space()='Confirmar' or normalize-space()='OK']]"
    )

    # === REPORTS - Exportação ===
    CONFIRMAR = (By.XPATH, "//button[contains(@class,'ids-main-button')][.//span[normalize-space()='Confirmar']]")
    EXCEL = (By.XPATH, "//ids-form-selection//span[contains(@class,'ids-label')][.//span[normalize-space()='Excel']]")
    EXPORT_EXCEL_BTN = (By.CSS_SELECTOR, "button[aria-label*='Excel'][type='button'], button[aria-label*='excel'][type='button']")
    EXPORT_EXCEL_BTN_ALT = (By.XPATH, "//button[@type='button' and contains(@aria-label, 'Excel')]")
    BAIXAR = (By.XPATH, "//button[contains(@class,'ids-main-button')][.//span[contains(normalize-space(),'Baixar relatório')]]")

    # === EXTRATO ===
    EXTRATO_PERIODO_TRIGGER = (By.ID, "periodoFiltro")
    EXTRATO_PERIODO_PERSONALIZADO = (By.XPATH, "//li[@data-id='personalizado' or contains(normalize-space(), 'personalizado')]")
    EXTRATO_DATE_INICIAL = (By.ID, "date-mask-custom-inicial")
    EXTRATO_DATE_FINAL = (By.ID, "date-mask-custom-final")
    EXTRATO_FILTRAR = (By.ID, "btn-aplicar-filtros")
    EXTRATO_EXPORT_MENU = (By.ID, "botao-opcoes-lancamentos")
    EXTRATO_EXPORT_EXCEL = (By.XPATH, "//a[contains(@onclick,'abrirExportarExcel')]")
    EXTRATO_EXCEL_CHECKBOXES = (By.CSS_SELECTOR, "input.excel-check-input")
    EXTRATO_EXCEL_SAVE = (By.ID, "salvar-excel-botao")
    EXTRATO_LOADING = (By.CSS_SELECTOR, "div.loading-nova-internet[aria-label='carregando']")
    
    # === LOGOUT ===
    # === LOGOUT ===
    SAIR = (By.ID, "linkSairHeader")
    SAIR_SIM = (By.XPATH, "//a[contains(@class,'itau-button')][.//span[normalize-space()='sim']]")
