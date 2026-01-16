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
    
    # === LOGOUT ===
    SAIR = (By.XPATH, "//a[contains(@class,'btn-nav')][.//span[normalize-space()='sair']]")
    SAIR_SIM = (By.XPATH, "//a[contains(@class,'itau-button')][.//span[normalize-space()='sim']]")
