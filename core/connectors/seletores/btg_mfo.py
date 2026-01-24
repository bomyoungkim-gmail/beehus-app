from dataclasses import dataclass
from selenium.webdriver.common.by import By


@dataclass(frozen=True)
class SeletorBtgMfo:
    """Selectors for the BTG MFO portal."""

    URL_BASE = "https://www.btgpactual.com/home"

    # Login
    LOGIN_FIELD = (By.CSS_SELECTOR, 'input[name="login"]')
    PASSWORD_FIELD = (By.CSS_SELECTOR, 'input[name="password"]')
    TOKEN_FIELD = (By.CSS_SELECTOR, 'input[name="softToken"]')
    SUBMIT_BUTTON = (By.CSS_SELECTOR, "button[name='entrar'][type='submit']")
    LOGIN_ERROR = (By.CLASS_NAME, "authenticate-panel__form--error-message")

    # Navigation - Client Selection
    CLIENT_SELECTION_BUTTONS = (By.ID, "selectClientButton")
    ACCESS_BUTTON = (By.XPATH, ".//button[text()='Acessar >']")
    OPERATION_BUTTON = (By.ID, "operation_button")

    # Navigation - Reports
    REPORTS_WM_FEATURE = (By.ID, "feature[object Object]1_button")

    # Report Selection - Category
    CATEGORY_SELECT = (By.CSS_SELECTOR, '[placeholder^="Selecione uma categoria"]')
    CATEGORY_INVESTMENT = (By.XPATH, "//li[text()='Investimento']")

    # Report Selection - Report Type
    REPORT_SELECT = (By.XPATH, "//*[starts-with(@placeholder, 'Selecione um relat')]")
    REPORT_INVESTMENT_WM = (By.XPATH, "//li[text()='Investimentos (WM Externo) (D-1 e D0)']")
    FILTER_BUTTON = (By.ID, "--button")

    # Power BI iframe
    POWERBI_IFRAME = (By.XPATH, '//iframe[contains(@src, "https://app.powerbi.com/reportEmbed?reportId=87ba81d5-79c7-4dd0-ad91-2ec526a10e99")]')

    # Power BI - Positions Download
    POSITIONS_BUTTON_CONTAINER = (By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[37]/transform/div/div[3]/div/div/visual-modern/div')
    POSITIONS_TILE = (By.CLASS_NAME, 'tile')
    POSITIONS_BUTTON = (By.CLASS_NAME, 'sub-selectable')
    POSITIONS_DATE_SELECT = (By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[14]/transform/div/div[3]/div/div/visual-modern/div/div/div[2]/div')
    POSITIONS_DZERO_OPTION = (By.XPATH, '/html/body/div[16]/div[1]/div/div[2]/div/div[1]/div/div/div[1]/div')
    POSITIONS_TITLE = (By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[44]/transform/div/div[3]/div/div/div/div/div/div/h3')
    POSITIONS_MENU_BUTTON = (By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[44]/transform/div/visual-container-header/div/div/div/visual-container-options-menu/visual-header-item-container/div/button')

    # Power BI - Transactions Download
    TRANSACTIONS_BUTTON_CONTAINER = (By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[29]/transform/div/div[3]/div/div/visual-modern/div')
    TRANSACTIONS_TITLE = (By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[43]/transform/div/div[3]/div/div/div/div/div/div/h3')
    TRANSACTIONS_MENU_BUTTON = (By.XPATH, '/html/body/div[3]/report-embed/div/div/div[1]/div/div/div/exploration-container/div/div/docking-container/div/div/div/div/exploration-host/div/div/exploration/div/explore-canvas/div/div[2]/div/div[2]/div[2]/visual-container-repeat/visual-container[43]/transform/div/visual-container-header/div/div/div/visual-container-options-menu/visual-header-item-container/div/button')

    # Power BI - Export Dialog (shared)
    EXPORT_DATA_BUTTON = (By.XPATH, '//*[@id="0"]')
    DOWNLOAD_BUTTON = (By.XPATH, '/html/body/div[4]/div[2]/div/mat-dialog-container/div/div/export-data-dialog/mat-dialog-actions/button[1]')
