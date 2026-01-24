from dataclasses import dataclass
from selenium.webdriver.common.by import By


@dataclass(frozen=True)
class SeletorBtgOffshore:
    """Selectors for the BTG Offshore portal."""

    URL_BASE = "https://app.btgpactual.com/login"

    # Login
    EMAIL = (By.CSS_SELECTOR, "input#email")
    PASSWORD = (By.CSS_SELECTOR, "input#password")
    SIGN_IN = (By.XPATH, "//button[normalize-space()='Sign in']")
    PORTAL_GLOBAL = (By.CSS_SELECTOR, "fieldset.login__external-link")

    # OTP
    OTP_CODE = (By.ID, "code")
    OTP_CONTINUE = (By.XPATH, "//button[normalize-space()='Continue']")

    # Country selection
    COUNTRY_US = (By.XPATH, "//div[contains(@class,'orq-tabs__tab')]//span[normalize-space()='United States']")

    # Accounts
    CHECKBOX_TOTAL = (By.CSS_SELECTOR, "orq-checkbox#Checkbox_TotalAccount input")
    ACCOUNT_CHECKBOXES = (By.CSS_SELECTOR, "input[type='checkbox'][aria-label='Checkbox']")
    ACCESS_BTN = (By.XPATH, "//button[normalize-space()='Access']")

    # Modal
    DONT_SHOW_AGAIN = (By.XPATH, "//span[normalize-space()=\"Don't show again\"]")
    MODAL_OVERLAY = (By.CSS_SELECTOR, "div.orq-modal__overlay")
    MODAL_CLOSE_BUTTON = (By.CSS_SELECTOR, "button.orq-modal__close-button")
    MODAL_CLOSE = (By.CSS_SELECTOR, "button[aria-label='Close'], button.close, .icon-close")
    MODAL_SKIP = (By.XPATH, "//button[contains(normalize-space(), 'Skip') or contains(normalize-space(), 'Close')]")

    # Filters / export
    DATE_INPUT = (By.CSS_SELECTOR, "input[placeholder*='Data de']")
    CHECK_ALL_ANCHOR = (By.CSS_SELECTOR, "a.see-more")
    EXPORT_OPTIONS_BTN = (By.XPATH, "//button[.//span[contains(normalize-space(),'Export options')]]")
    EXPORT_ALL_OPTION = (By.XPATH, "//div[contains(@class,'menu-expanded')]//div[normalize-space()='Export all']")

    SIDEBAR_TOGGLE = (By.CSS_SELECTOR, "button.burguer-menu-button")
    SIDEBAR_PORTFOLIO = (By.XPATH, "//button[.//p[normalize-space()='Portfolio']]")
    PORTFOLIO_CHECK_ALL = (By.XPATH, "//a[.//span[normalize-space()='Check all']]")

    FILTERS_BTN = (By.XPATH, "//button[normalize-space()='Filters']")
    TIME_PERIOD = (By.XPATH, "//label[.//span[normalize-space()='Time Period']]")
    CUSTOM_PERIOD = (By.XPATH, "//div[contains(@class,'description') and normalize-space()='Custom period']")
    CUSTOM_DATE_INPUTS = (By.CSS_SELECTOR, "input[placeholder*='Click and select']")
    FILTER_BTN = (By.XPATH, "//button[normalize-space()='Filter']")
    EXPORT_BTN = (By.XPATH, "//button[normalize-space()='Export']")
    DOWNLOAD_BTN = (By.XPATH, "//button[normalize-space()='Download']")

    # Logout
    PROFILE_MENU = (By.ID, "menuProfile")
    CHANGE_CUSTODY = (By.XPATH, "//div[contains(@class,'header__menu--changeCountry')]//p[normalize-space()='Change custody']")
    COUNTRY_CAYMAN = (By.XPATH, "//div[contains(@class,'orq-tabs__tab')]//span[normalize-space()='Cayman Islands']")
    SIGN_OUT = (By.XPATH, "//div[contains(@class,'header__menu--signout')]//p[normalize-space()='Sign Out']")
